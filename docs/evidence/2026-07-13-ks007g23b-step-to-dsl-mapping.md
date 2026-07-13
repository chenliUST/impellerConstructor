# KS007G23B STEP-To-DSL Mapping

Date: 2026-07-13

## Scope And Authority

This record analyzes the customer-supplied `KS007G23B.stp` and creates the
separate review preset `ks007g23b_step_reconstructed_v1_1`. It does not replace
the drawing-only preset. The source SHA-256 is
`1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5`.

The imported STEP B-Rep is authoritative for its own topology and dimensions.
The generated V1.1 preset is not authoritative CAD: it reduces the STEP into the
existing six-point support-profile, scalar thickness, scalar pose, and five-loop
surface-family semantics.

Analysis runtime: OCCT/OCP 7.9.3.1 and CadQuery 2.8.0. The STEP header identifies
Creo Parametric 2023073 and `CONFIG_CONTROL_DESIGN`.

## Exact B-Rep Facts

| Fact | STEP result | Confidence |
| --- | ---: | ---: |
| Solids / shells | 1 / 1 | 1.00 |
| Faces / edges / vertices | 240 / 666 / 433 | 1.00 |
| Volume | 61526.200588 mm3 | 1.00 |
| Surface area | 34153.811858 mm2 | 1.00 |
| True topology outer radius | 51.6000 mm | 1.00 |
| Overall axial extent | 36.5000 mm | 1.00 |
| Main cylindrical bore radius | 7.9000 mm | 1.00 |
| Auxiliary holes | 3 x R2.0000 mm | 1.00 |
| Periodic blade population | 13 at 27.6923077 deg pitch | 1.00 |

The loose X/Y B-spline face bounding box exceeds R51.6 slightly. Topology
vertices and the analytic outer cylinder confirm that this is a bounding
tolerance effect, not a larger nominal diameter.

## Freeform Surface Measurements

The two principal blade-side B-spline families repeat 13 times and have areas of
approximately 602.0 and 467.8 mm2 per blade. Their normalized parameter domains
were paired with opposite span orientation before measuring separation.

| Reduced quantity | STEP measurement | Preset value | Confidence |
| --- | ---: | ---: | ---: |
| Mean paired PS/SS separation | 5.187 mm | 5.2 mm | 0.90 |
| 95th percentile PS/SS separation | 6.566 mm | 6.6 mm | 0.85 |
| Camber wrap over five span samples | 30.95 to 32.89 deg | 32.0 deg | 0.90 |
| Midspan integrated S-Q turn | 15.331 mm | 15.3 mm | 0.85 |
| Across-span S-Q turn range | 10.942 to 19.318 mm | 8.4 mm delta | 0.75 |
| Midstream root-to-tip phase change | about 5.8 deg | 5.8 deg lean | 0.78 |
| Inlet root-to-tip phase change | about 2.7 deg | 2.7 deg LE lean | 0.75 |
| Outlet root-to-tip phase change | about 0.7 deg | 0.7 deg TE lean | 0.70 |
| Root patch transverse width | about 1.5 to 2.0 mm | 1.8 mm | 0.80 |
| Root patch axial separation | about 0.7 to 1.5 mm | 1.2 mm | 0.75 |

The STEP result corrects two weak drawing-only assumptions: blade thickness was
seeded at 1.2 mm but is about 5.2 mm on average, and wrap was seeded at 82 deg but
the measured camber wrap is about 32 deg.

## Reduced Support Profiles

The upper hub profile was sampled from a periodic B-spline hub support face. The
tip profile was sampled along the center of the repeated B-spline tip cap.

```text
hub R-Z mm:
(12.5000,25.0000) (16.1827,15.6288) (22.7520,8.0011)
(31.4809,2.9762) (41.2849,0.5809) (51.3767,0.0000)

tip R-Z mm:
(31.7359,25.0593) (32.9576,19.1349) (35.8846,13.8436)
(40.2573,9.6642) (45.6181,6.8529) (51.5001,5.3997)
```

These are points on the source surfaces, then reused as six V1.1 profile
controls. Because sampled points are not the original STEP NURBS poles, the
profile confidence is 0.92 for the hub and 0.90 for the tip rather than 1.00.

## Confidence Changes From Drawing-Only Preset

| Concept | Drawing-only | STEP-reduced | Reason |
| --- | ---: | ---: | --- |
| Blade count | 1.00 | 1.00 | STEP independently confirms periodicity |
| Outer radius | 1.00 | 1.00 | Exact topology envelope |
| Main bore radius | 0.90 | 1.00 | Exact analytic cylinder |
| Hub support profile | 0.55 | 0.92 | Direct B-spline support sampling |
| Tip support profile | 0.50 | 0.90 | Direct B-spline cap sampling |
| Blade thickness | 0.25 | 0.90 | Paired source-surface sampling |
| Blade wrap | 0.35 | 0.90 | Five-span camber measurement |
| Lean values | 0.25 | 0.70-0.78 | Span phase measurement |
| Root width/lift | 0.25 | 0.75-0.80 | Root patch boundary measurement |
| Constant fillet/edge radii | 0.20 | 0.40-0.50 | Source edges are freeform B-splines |

## Deliberate Losses

- The source STEP's exact pressure, suction, edge, tip, and root B-spline faces.
- The stepped DIN5480 spline bore and its local transitions.
- Three auxiliary holes, detailed conical edge treatments, and balancing details.
- Face identity, tolerances, GD&T, surface finish, heat treatment, and machining
  semantics.
- Exact mass agreement. STEP volume multiplied by typical GH4169 density gives
  roughly 505 g; the drawing states 516.7 g. Alloy condition/density and drawing
  mass authority are not sufficient to classify the difference as an error.

The UI and export manifests must therefore continue to label the generated
preset `review-grade` and must point users to the original STEP for source CAD.
