# Impeller Frontend Visualization Design

Date: 2026-06-29
Project: Part Rule Synthesis
Status: Approved for first implementation

## Goal

Build an independent React frontend that lets a user generate and inspect impeller variants from
the existing rule engine. The first version focuses on visual testing: compare presets, adjust
parameters, regenerate STL exports, and view the result as shaded, wireframe, or combined shaded plus
wireframe geometry.

Implementation note: local `npm`, `pnpm`, and `npx` package installation stalled in this workspace.
The delivered v0.1 therefore uses browser ESM import maps for React and Three.js and is served as a
static frontend. The component/module layout remains compatible with a later Vite migration.

## Scope

The frontend shall provide:

- A preset browser for several radial/backward-curved impeller variants.
- Parameter controls for blade count, inlet/exit radii, blade heights, blade angles, blade thickness,
  blade curve gain, and hub curve height.
- A Three.js STL viewer with orbit controls, reset view, shade/wireframe toggles, and generated model
  reload.
- A manifest panel showing run id, validation status, source references, selected parameters, operation
  graph, and STEP/STL export links.
- Clear status and error messages for generation failures.

The first version shall not implement a full CAD feature tree, direct mesh editing, physical
performance optimization, or the new `impeller + facets + preset` backend ontology. It shall display
facet-like labels in the UI while continuing to use the existing `centrifugal_impeller` compatibility
rule engine.

## Architecture

The backend remains the source of deterministic geometry generation. The frontend calls:

- `POST /api/rule-engines/synthesize` with `part_family_id: "centrifugal_impeller"`.
- `POST /api/rule-engines/{engine_id}/instantiate` with selected parameters.
- `GET /api/model-runs/{run_id}/exports/stl` for Three.js loading.
- `GET /api/model-runs/{run_id}/exports/step` for download.

The frontend stores only transient UI state. Presets are local frontend data in v0.1 because the backend
ontology preset migration is a separate task.

## Frontend Components

- `App`: owns selected preset, parameters, generated manifest, loading/error state, and layout.
- `PresetList`: lets users switch between predefined visual variants.
- `ParameterPanel`: renders typed numeric inputs and range controls.
- `ModelViewer`: loads the current STL export and renders shaded/wireframe modes using Three.js.
- `ManifestPanel`: displays validation, exports, operation graph, and selected parameters.

## Presets

Initial presets:

- `reference`: UPCommons-derived radial backward-curved single-suction reference.
- `high-curvature-a`: higher blade curve gain and curved hub.
- `high-curvature-b`: taller inlet and stronger hub curvature.
- `compact`: smaller radial envelope for faster visual iteration.

All presets shall be honest about their current generator: `part_family_id` remains
`centrifugal_impeller` until the ontology refactor lands.

## Error Handling

- Parameter values are clamped to backend-safe ranges before submission.
- Backend 400 responses are shown in the UI with the backend message.
- STL loading failures keep the last valid manifest visible and show a viewer error.
- Empty or missing manifests render a neutral empty state rather than crashing the UI.

## Testing

Backend tests:

- API accepts browser CORS preflight for local frontend development.
- The impeller generator accepts the frontend's parameter range for visual variants.

Frontend tests:

- Presets produce valid bounded payloads.
- API URL helpers build correct export URLs.
- Manifest helpers extract validation and export state without requiring the Three.js viewer.

Manual visual verification:

- Start FastAPI and the frontend static dev server.
- Generate the reference and high-curvature presets.
- Confirm STL appears, orbit controls work, and shaded/wireframe/combined modes visibly switch.
