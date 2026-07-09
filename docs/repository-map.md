# Repository Map

This document records the intended ownership boundaries of the repository. It is meant to make future ontology/DSL/kernel iterations easier to navigate.

## Top-Level Layout

| Path | Responsibility |
| --- | --- |
| `README.md` | Project entry point, current status, quick start, and version lineage. |
| `pyproject.toml` | Python package metadata and pytest configuration. |
| `src/part_rule_synthesis/` | Backend rule synthesis service and geometry generation code. |
| `frontend/` | Browser frontend for interactive impeller inspection. |
| `tests/` | Python acceptance/unit tests for backend DSL, kernels, manifests, and workflow. |
| `docs/` | Research notes, design specs, plans, evidence, and generated explanatory diagrams. |
| `scripts/` | Local research and verification scripts. |
| `videos/` | Visual sweep evidence and HyperFrames video artifacts. |

## Backend Modules

| Module | Responsibility |
| --- | --- |
| `api.py` | FastAPI entrypoint and HTTP API composition. |
| `service.py` | Rule synthesis orchestration, instantiation, manifests, export paths, and feedback APIs. |
| `impeller_dsl_resources.py` | Loading versioned JSON DSL/ontology resources from package paths. |
| `impeller_runtime_compiler.py` | Compiling versioned impeller DSL presets into runtime dictionaries. |
| `impeller_surface_graph_export.py` | Graph-derived STL and faceted STEP export writer with surface-region provenance. |
| `impeller_brep_export.py` | OCP/OCCT writer for V0.6 graph-derived unsewn NURBS/analytic B-Rep support faces. |
| `impeller_bounded_brep_export.py` | OCP/OCCT writer for V0.7 bounded, unsewn B-Rep faces and STEP reimport bbox validation. |
| `impeller_cad_payload.py` | CAD payload helpers for exportable graph surfaces and edges. |
| `impeller_mesh_export.py` | OBJ surface-graph mesh writer with transition-region provenance. |
| `impeller_mesh_manifest.py` | CFD surface mesh inspection manifest and transition-region summaries. |
| `impeller_shape_control.py` | Shape control normalization and compatibility helpers. |
| `impeller_design_space.py` | v0.4 campaign signatures, topology freezing, and design vector contracts. |
| `impeller_graph_contract.py` | Surface graph utility contracts, wetted-surface filtering, and area estimation. |
| `impeller_cfd_manifest.py` | CFD full-360 patch group, patch instance, and surface mesh inspection manifest generation. |
| `impeller_v10_closed_profile.py` | V1.0 closed blade section profile builder for pressure/suction and leading/trailing cap curves. |
| `impeller_v10_blade_faces.py` | V1.0 native blade face network generator. |
| `impeller_v10_hub_profile.py` | V1.0 native hub, bore, and bevel revolve face generator. |
| `impeller_v10_topology_graph.py` | V1.0 shared-edge topology graph builder. |
| `impeller_v10_surface_graph.py` | V1.0 surface graph integration combining hub faces, blade faces, and topology graph. |
| `impeller_v11_blade_to_blade_loop.py` | V1.1 blade-to-blade loop-family builder, main/splitter passage positioning, edge-cap construction, and loop metrics. |
| `impeller_v11_surface_family.py` | V1.1 shared-boundary surface-family graph for blade faces, root/tip/shroud attachments, and hub material review faces. |
| `impeller_v11_loop_validation.py` | V1.1 loop-family validation for domain metadata, main/splitter invariants, and measured C2/G2 joins. |
| `impeller_v11_validation.py` | V1.1 surface-family validation gates and failure reporting. |
| `impeller_kernels/axisymmetric_throughflow_nurbs.py` | Main axisymmetric throughflow NURBS impeller geometry kernel. |
| `impeller_kernel.py` | Earlier impeller geometry kernel/proxy support retained for compatibility. |
| `impeller_taxonomy.py` | Facet taxonomy and preset support outside the v0.4 slice. |

## Versioned DSL And Ontology

| Path | Meaning |
| --- | --- |
| `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_2` | First focused slice contract. |
| `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_3` | Solid hub/hood and staged interactive curve workflow. |
| `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_4` | Optimization-ready surface/feature graph and CFD full-360 view. |
| `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_5` | Surface-graph-faithful export contract and export-region provenance. |
| `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_6` | NURBS/analytic B-Rep support-face STEP export, mesh inspection manifest, Model Output artifacts, and explicit fillet/blend controls; trim-loop/wire export remains future work. |
| `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_7` | Bounded B-Rep face export, edge-family transition policies, OBJ mesh artifacts, and mesh overlay inspection contract. |
| `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v0_91` | Topology-first transition scaffold for V0.9 transition validity. |
| `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_0` | Topology-first native blade, root, hub, bore, and bevel face constructor contract. |
| `src/part_rule_synthesis/dsl/impeller/axisymmetric_throughflow_radial_bladed/v1_1` | Blade-to-blade five-loop surface-family constructor, V1.1.1 representative preset catalog, main/splitter passage-bisector semantics, half-thickness edge caps, shared-boundary UV mesh contract, and V1.1 golden cases. |
| `src/part_rule_synthesis/ontology/impeller/v0_2` | Ontology resources aligned with v0.2. |
| `src/part_rule_synthesis/ontology/impeller/v0_3` | v0.3 ontology slice marker. |
| `src/part_rule_synthesis/ontology/impeller/v0_4` | Ontology resources aligned with v0.4. |

V1.1 ontology semantics are currently encoded in the DSL `v1_1` schema, constructors, export contracts, capability matrix, and golden-case registry rather than in a separate `src/part_rule_synthesis/ontology/impeller/v1_1` folder.

Each DSL version should remain loadable through tests after newer versions are added.

## Frontend Modules

| Module | Responsibility |
| --- | --- |
| `src/App.js` | Application composition, API base, preset selection, parameter state, and viewer wiring. |
| `src/appModel.js` | Frontend preset definitions, parameter schema, facet schema, and API payload builders. |
| `src/apiClient.js` | HTTP client for synthesis, instantiation, and export URLs. |
| `src/workspaceModel.js` | Geometry layer schema and layer classification. |
| `src/simulationViewModel.js` | CAD/CFD/feature-debug simulation views and CFD patch selection helpers. |
| `src/edgeTreatmentModel.js` | V0.7 edge-family treatment defaults, transition override payloads, and UI-facing summaries. |
| `src/meshOverlayModel.js` | Mesh overlay state and transition-region highlighting helpers for OBJ/mesh inspection. |
| `src/profileEditorModel.js` | 2D meridional profile editor math. |
| `src/bladeCurveEditorModel.js` | Blade intrinsic curve editor math. |
| `src/components/ModelViewer.js` | Three.js model viewer, surface graph rendering, construction lines, and CFD highlighting. |
| `src/components/CfdManifestPanel.js` | CFD patch group summary and patch selection UI. |
| `src/components/MeshInspectionPanel.js` | Mesh quality and transition-region inspection panel. |

## Evidence And Research Docs

| Path | Meaning |
| --- | --- |
| `docs/superpowers/specs/` | Human-reviewed design specs and literature/analysis outputs. |
| `docs/superpowers/plans/` | Implementation plans used to execute code changes. |
| `docs/evidence/` | Screenshots and records of observed issues or visual verification. |
| `docs/impeller_parameter_diagrams/` | Algorithm-generated diagrams explaining parameter meaning. |
| `docs/axisymmetric-throughflow-nurbs-kernel.md` | Current kernel construction order and v0.4 graph contract. |
| `docs/current-research-frontier.md` | Canonical statement of what the current repository can and cannot claim. |
| `docs/evidence-policy.md` | Rules for committing evidence artifacts and large generated outputs. |
| `docs/evidence/2026-07-01-impeller-v0-5-surface-graph-faithful-export/` | User-supplied mismatch screenshots and analysis motivating implemented v0.5 export semantics. |
| `docs/evidence/2026-07-01-impeller-v0-6-trimmed-nurbs-brep-export/` | Follow-up third-party STEP limitation evidence plus V0.6 NURBS/analytic B-Rep support-face implementation evidence and remaining trim-loop/wire and manual CAD import gaps. |
| `docs/evidence/2026-07-02-impeller-v0-7-bounded-transitions-and-mesh/` | V0.7 bounded face, edge transition policy, OBJ mesh artifact, mesh overlay, and OCCT reimport bbox evidence. |
| `docs/evidence/2026-07-05-impeller-v1-0-topology-first/` | V1.0 semantic-change, public-reference, diagnostic, insight, and test-transcript evidence. |
| `docs/evidence/2026-07-08-impeller-v1-1-milestone-summary.md` | V1.1 milestone index covering construction logic, DSL resources, ontology-slice boundary, implementation map, validation, and evidence links. |
| `docs/evidence/2026-07-08-impeller-v1-1-preset-hub-solid-display-evidence.md` | V1.1 correction evidence for preset shape, hub solid display, root/tip/shroud attachment, half-thickness edge caps, and splitter passage-bisector positioning. |
| `docs/evidence/2026-07-08-impeller-v1-1-1-viewer-preset-parameter-overhaul-evidence.md` | V1.1.1 evidence for viewer mode semantics, all-surface CFD360 mesh inspection, five-preset active catalog, preset-owned parameters, and service smoke triangle counts. |

## Scripts

| Path | Meaning |
| --- | --- |
| `scripts/verify_repository.ps1` | PowerShell verification entrypoint for fast and full repository checks. |
| `scripts/verify_version_lineage.ps1` | Verifies current DSL folders and historical git tags can synthesize and instantiate their presets. |
| `scripts/impeller_parameter_experiment.py` | Parameter-sweep research script retained for diagnostic experiments. |
| `scripts/render_impeller_parameter_diagrams.py` | Generates explanatory parameter diagrams under `docs/impeller_parameter_diagrams/`. |

## Working Rules

1. Put new ontology/DSL semantics in a new version folder when old semantics are research evidence.
2. Keep backend tests covering each loadable DSL version.
3. Keep frontend presets pointed at the latest interactive study version unless a legacy workflow is explicitly needed.
4. Keep generated videos/screenshots out of routine code commits unless they are deliberate evidence artifacts.
5. Treat certified manufacturing CAD, production meshing, CAE solver adapters, and CAM feedback as separate future integration layers.
6. Keep `docs/current-research-frontier.md` aligned with README claims before presenting the project externally.
