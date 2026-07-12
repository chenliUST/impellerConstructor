# Impeller V1.1.5 Engineering Drawing Fidelity Implementation Plan

## Goal

Upgrade the read-only review drawing from sparse sampled boundaries to a
generation-bound engineering presentation of the complete resolved V1.1.2
geometry and its canonical construction parameters.

## Compatibility Boundary

- Runtime release and drawing contract advance to `1.1.5`.
- Canonical NURBS geometry and geometry patch remain `1.1.2`.
- Historical parameter-inspection contract remains `1.1.4`.
- Stable V1.1 preset ids and preset-only instantiation remain unchanged.

## Tasks

1. Add a V1.1.5 drawing builder with dense adaptive support-profile sampling,
   actual blade-surface Top projection, material sections, five-span S-Q loops,
   XYZ loop overlays, construction tables and a complete parameter registry.
2. Add cached, generation-bound full-contract, per-view and construction-table
   API endpoints.
3. Render the Top sheet from surface boundaries, restore hub and bore circles,
   and show root/mid/tip sections for both main and splitter blades.
4. Render the Meridional sheet with actual NURBS curves, dashed control polygons,
   conventional material hatching and an orthographic side-view inset.
5. Render five S-Q stations for every present blade class and overlay the same
   resolved XYZ loops on enlarged high-DPI representative blade scenes.
6. Add construction tables and an auditable registry assigning every canonical
   parameter leaf to a drawing, table, quality record or not-applicable record.
7. Keep the active UI read-only and load drawing views on demand to bound browser
   memory and rendering work.
8. Verify backend contracts, all frontend tests, frontend build and live browser
   rendering for representative presets.

## Acceptance

- No Top blade geometry is sourced from a section loop.
- Top includes hub outer/inner and mounting-bore topology.
- Meridional actual profiles are distinct from their control polygons and use at
  least 129 samples with measured chord error no greater than 0.1 mm.
- Main and splitter rows each expose five S-Q and five XYZ loop stations when
  present.
- The canonical parameter registry has zero unaccounted leaves.
- Drawing view changes do not blank the page or construct additional WebGL
  renderers per section.
