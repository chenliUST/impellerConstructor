# Impeller v0.4 Optimization-Ready Surface/Feature Graph Evidence

Date: 2026-07-01

Related spec:

- `docs/superpowers/specs/2026-07-01-impeller-v0-4-optimization-ready-surface-feature-graph-design.md`

## 1. Starting Feedback

The v0.3 impeller geometry and parameters were accepted as a current baseline, but the
user identified these gaps before the next ontology/DSL upgrade:

1. Edge round/chamfer transition rules appear declared but not materially implemented
   in the frontend-visible geometry.
2. Other feature rules, such as mounting holes and slots, are not yet planned clearly.
3. NURBS curve control-point counts are fixed and too limited for large features such
   as hub surface, tip surface, and blade iso-v lines.
4. The current iso-u line construction is unclear. The user emphasized that blade
   surfaces are not necessarily ruled surfaces.
5. The project should eventually become part of a high-throughput CAD/CAE integrated
   workflow.

## 2. Current-Code Diagnosis

Local code review found:

- v0.3 DSL declares hub/hood chamfer parameters and solid features.
- `axisymmetric_throughflow_nurbs.py` contains sampled chamfer-band and blade-edge
  closure surfaces, but these are research-grade surfaces rather than exact CAD
  fillet operations.
- Hub/tip profile override validation is fixed to exactly four cubic control points.
- Frontend profile validation also requires exactly four control points.
- Blade intrinsic curves already allow variable point counts in backend validation,
  but defaults and UI are still sparse.
- Current blade iso-u construction is sampled from `mean_surface[u_index][v]`, not
  directly authored as an editable spatial NURBS curve.

## 3. Discussion Decisions

The following choices were made during the 2026-07-01 design discussion:

1. v0.4 should use a balanced upgrade scope, not a single-feature patch.
2. Feature grammar should define both assembly/manufacturing features and tuning
   features, but v0.4 should only implement assembly/manufacturing features.
3. Blade surface modeling should follow boundary + guide/layer curves, not remain
   purely field-driven and not expose raw tensor-product NURBS as the first user-facing
   authoring model.
4. Because the future target is high-throughput CAD/CAE, v0.4 must freeze control
   topology inside optimization campaigns.
5. Use CFD + FEA dual simulation views.
6. Make CFD executable-first; FEA stays schema-level in v0.4.
7. Use full 360 CFD wetted geometry as the first executable CFD view.
8. Use group + instance patch naming.
9. Use surface/feature graph compiler architecture.

## 4. Visual Companion Screens

A local Superpowers visual companion session was used to structure the discussion.
Those files are intentionally not committed because they live in `.superpowers/`, a
local temporary collaboration directory.

Screens shown:

1. `v04-scope-map.html` - four upgrade pressure points.
2. `blade-surface-parameterization.html` - field-driven, boundary-guided, and full
   tensor-product options.
3. `cad-cae-optimization-stack.html` - CAD/CAE optimization-ready contract layers.
4. `dual-simulation-view.html` - CFD and FEA view split.
5. `cfd-domain-choice.html` - full 360, periodic sector, or both.
6. `v04-architecture-options.html` - incremental patch, graph compiler, or full
   CAD/CAE platform.

## 5. Industry/Research Evidence

The design discussion used these public sources to align with industry terminology:

- CFturbo impeller design workflow:
  - <https://cfturbo.com/software/impellers>
  - <https://manual.cfturbo.com/en/mercon.html>
  - <https://manual.cfturbo.com/en/x-beta-blade-angle-progression.html>
  - <https://manual.cfturbo.com/en/prof.html>
- Ansys BladeModeler radial blade design and angle/thickness workflow:
  - <https://www.ansys.com/products/fluids/ansys-blademodeler>
  - <https://www.aprens.com/pdfs_V11.0/blademodeler11.pdf>
- Concepts NREC AxCent blade stacking, mid-span sections, swept edges, and fillets:
  - <https://www.conceptsnrec.com/axcent-software>
- ADT TURBOdesign inverse design and blade loading workflow:
  - <https://www.adtechnology.com/products/3d-inverse-design-turbomachinery>
  - <https://blog.adtechnology.com/what-is-blade-loading>
- Research examples for B-spline/NURBS blade parameterization:
  - <https://repository.tudelft.nl/file/File_f54e874b-a8e0-4c84-8f5b-912f7dd289f7>
  - <https://www.mdpi.com/2226-4310/9/9/489>

## 6. Resulting v0.4 Direction

The chosen v0.4 design is:

```text
Optimization-ready surface/feature graph compiler
```

The compiler should transform DSL instances into:

- CAD review surface/feature graph,
- full 360 CFD wetted geometry manifest,
- schema-level FEA view,
- stable patch groups and patch instances,
- campaign signature and design-vector contract,
- validity report usable for future loss records.

This evidence log should remain part of the repository so later DSL versions can trace
why v0.4 introduced the graph/manifest layer.

