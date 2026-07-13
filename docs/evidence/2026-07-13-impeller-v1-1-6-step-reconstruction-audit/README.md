# Impeller V1.1.6 STEP Reconstruction Audit Evidence

Date: 2026-07-13

## Scope

This evidence certifies the V1.1.6 STEP audit workflow on the supplied
KS007G23B STEP file. It does not promote the reconstructed result beyond
review-grade and does not change the canonical V1.1.2 NURBS constructor.

Source STEP authority:

```text
SHA-256 1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5
Size    5,583,108 bytes
Schema  CONFIG_CONTROL_DESIGN
```

Runtime:

```text
Python   3.12.10
CadQuery 2.8.0
OCP/OCCT 7.9.3.1
Audit    1.1.6
Geometry 1.1.2
```

## Acceptance Result

The complete local audit passed in 81.376 seconds. It recovered one solid,
240 faces, 666 edges, 433 vertices, R51.6 outer topology, R7.9 main bore,
36.500002 mm axial extent and a 13-fold population at 27.692307692 degrees.

The unchanged V1.1.2 constructor passed all three stages:

| Stage | Validation | Duration |
| --- | --- | ---: |
| hub support | PASS | 14.561 s |
| blade surfaces | PASS | 15.953 s |
| edge closures | PASS | 15.976 s |

All stages retained the same generation id
`a7455d82d987b118df0ae89d`; each stage has a distinct immutable input hash.
The final surface graph contains 84 surfaces.

The Windows persistence and periodic-phase correction was reverified through
HTTP with 463 status reads. The bounded, unsigned, mesh-sampled comparison now
reports:

| Metric | Value |
| --- | ---: |
| Bidirectional RMS | 2.110076 mm |
| Bidirectional median | 0.852196 mm |
| Bidirectional P95 | 4.819965 mm |
| Bidirectional maximum | 8.339690 mm |
| Top silhouette Hausdorff | 5.254113 mm |
| Meridional silhouette Hausdorff | 10.168447 mm |

These values expose the loss of the existing V1.1.2 reduced parameterization;
they are not evidence that the source STEP is inaccurate.

## Retention

The source STEP, canonical source STL, reconstruction STL and heatmap JSON remain
outside git. The compact result is in `ks007g23b-audit-summary.json`; test and
build commands are in `verification.txt`; limitations are in
`known-limitations.md`. The reproduced Windows failure and error budget are in
`windows-persistence-and-error-analysis.md`.
