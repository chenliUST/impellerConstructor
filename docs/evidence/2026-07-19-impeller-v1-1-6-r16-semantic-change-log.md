# Impeller V1.1.6 R16 Semantic Change Log

Date: 2026-07-19

## Contract Delta

- Audit implementation revision changes from
  `axis_first_triangle_surface_r15_3` to
  `axis_first_section_curve_authority_r16_23`. The direct section-curve surface
  subcontract remains `axis_first_section_curve_authority_r16_22`; R16.23
  changes STEP support-face semantics rather than blade-side construction.
- Authenticated STEP reconstruction may select
  `impeller_v1_1_6_direct_section_curve_network_r16_1`. Historical V1.1.2
  preset synthesis remains on its existing scalar-field constructor.
- Exact recovered section evidence now preserves source and canonical XYZ,
  physical meridional `S`, physical circumferential `Q`, display parameter
  `u`, carrier witnesses, source ids, endpoint witnesses, and closure class as
  separate fields. A normalized curve parameter is no longer accepted as a
  physical support parameter.
- Root and tip limits are S-dependent active-span fields. Interior section
  carriers interpolate between the measured local attachment boundaries
  instead of using one global support fraction.
- Pressure and suction curves retain independent streamwise intervals and
  endpoint stagger. Camber, pose, and normal thickness become derived
  inspection evidence and no longer reconstruct the STEP blade geometry.
- When STEP exposes one authenticated trimmed rational B-spline face for a
  blade side, that complete trimmed face is the geometry authority. Recovered
  section curves are analytic incidence constraints on the same face, not a
  second lossy UV loft. Sources without exact face authority remain on the
  direct curve-network loft. Source topology decides whether leading and
  trailing closures are shared sharp seams, measured closure curves, or finite
  edge surfaces.
- Root and tip attachment surfaces consume the actual retained blade and
  support boundaries. Trimmed source patches are sampled inside authenticated
  trim polygons rather than extended to a rectangular source-face domain.
- Finite root, tip, leading-edge, and trailing-edge faces are partitioned by
  the authenticated STEP semantic-face ledger. A tip candidate may no longer
  absorb LE/TE closure faces, and a sharp seam remains explicitly nonmaterial.
- Generated section overlays are reconstructed-surface intersections in the
  canonical frame. Source overlays are transformed exactly once and remain
  separately identified; source evidence is not reused as a generated loop.
- Periodic collision validation excludes explicitly nonmaterial seam
  placeholders and uses a three-dimensional triangle intersection narrow
  phase after bounded broad-phase tests.
- Deviation preprocessing triangulates each material UV surface once into a
  shared indexed mesh and reuses it for region and surface comparisons. The
  former whole-graph deep-copy and repeated graph triangulation path is
  removed.
- Deviation comparison is evaluated once per semantic source region against
  the union of all corresponding reconstruction patches. The surface ledger
  still proves coverage of every material face, while reverse source samples
  are no longer duplicated once per patch.
- A hub flowpath split into complementary trimmed STEP faces is now recovered
  as one semantic support union. Candidate faces must share the selected hub
  geometry type, be directly adjacent to an initially authenticated hub patch,
  have exactly one adjacent support owner, and conform to the preliminary
  meridional hub profile within bounded P95 and maximum residuals. Candidate
  expansion may not chain through a previously promoted face.
- Circumferential completeness is checked for every authenticated periodic
  instance. Exact trimmed-face boundary samples provide angular coverage;
  every expected pitch must retain both at least
  `0.8 * (360 / population_count)` degrees and at least 0.8 of its own
  population-median bare-hub coverage. Main and splitter populations may not
  share a count or median. A shared support patch must independently retain at
  least `0.8 * 360` degrees. Any unreadable, empty, one-point, or non-finite
  exact boundary edge fails closed. Incomplete coverage fails with
  `v116_hub_support_circumferential_coverage_incomplete`.
- A promoted complementary hub face inherits the periodic owner of its
  adjacent authenticated support patch. It is then reclassified as
  `hub_flowpath_support`, removed from blade, attachment, and section domains,
  and included in the supported-surface deviation scope.
- A periodic face adjacent to both the hub support and an authenticated blade
  side is protected as root attachment geometry, even when its profile
  residual is hub-like. Coarse representative instances preserve their source
  ledger but expose a sanitized construction domain with all promoted material
  support faces removed.
- `pattern_population_evidence`, the authority consumed by mapped pattern
  validation, is sanitized in full, not only at the selected representative.
  The original connected-component payload is retained separately as
  `coarse_pattern_population_evidence` for provenance and may not own material
  support faces.
- Audit progress now exposes `comparison_preprocessing` separately from
  `deviation_measured`. Preprocessing evidence records material surface and
  triangle counts, comparison-pair count, triangulation reuse, duration, and
  sampled process working set.

## Authority Boundary

- Direct section curves are authoritative only when authenticated STEP
  provenance, support correspondence, frame data, and source topology are
  complete.
- NURBS/scalar camber, pose, and thickness fields remain available for
  inspection and future editing, with authority
  `derived_from_direct_section_curve_network`.
- Meshes, UV lines, overlays, heatmaps, and exported review STL remain sampled
  review artifacts. They are not promoted to analytic B-Rep certification.
- R16 does not add spline grooves, auxiliary holes, keyways, the
  spline-modified bore, or the source bottom boss. Their unsupported status is
  unchanged.

## Stable Failure Policy

R16 rejects incomplete or contradictory direct-curve evidence instead of
falling back to the lossy scalar reconstruction. Stable failure families cover:

- missing or inconsistent coordinate-frame and carrier provenance;
- crossed, collapsed, or unbounded active-span fields;
- invalid curve orientation, material side, or closure classification;
- section-to-surface analytic incidence residual, row reversal, foldover, or
  shared boundary mismatch;
- attachment trim projection and authenticated trim-domain failures;
- periodic material collision and source-instance assignment failures.

## Preserved Semantics

- Runtime release remains V1.1.6 and canonical preset geometry remains
  V1.1.2.
- R15 axis polarity, named support endpoints, hub closure direction,
  comparison-frame identity, process-versus-geometry status, unsupported
  feature ledger, and corresponding-surface distance definitions are retained.
- Existing exact deviation mathematics is not weakened. R16 changes the
  geometry supplied to comparison and removes redundant preprocessing; it
  does not lower accuracy tolerances to obtain a passing result.
- A completed R16 audit remains review-only unless every explicit geometry,
  topology, correspondence, collision, and deviation acceptance gate passes.

## R16.24 Attachment Patch And Runtime Contract

- Audit and direct-surface implementation revision is
  `axis_first_attachment_patch_complex_r16_24`.
- A polygon-fallback trim partition may assign a STEP source edge id only to a
  subpatch edge that lies on the authenticated simplified trim path. Internal
  ear-clip diagonals and center spokes are `internal_patch_edge` and cannot
  create false shared-edge identity.
- Attachment continuity is split into regular-edge and endpoint-corner
  measurements. Coordinate sewing, G1, G2, and corner coupling are independent
  claims; overall continuity cannot pass when corner coupling fails.
- Authenticated source edges that are position-coincident but differentially
  discontinuous remain topologically matched and explicitly non-G1/non-G2.
  Reconstruction does not smooth away an observed source sharp edge.
- Generic and attachment topology candidate generation is indexed by bounded
  endpoint/semantic groups. The final coordinate and source-identity gates are
  unchanged.
- Dense review graphs use copy-on-write surface records during direct
  replacement and periodic/material decoration. Shared geometry arrays are
  read-only until the owning surface is replaced.
- Parameter-inspection generation ids retain their existing digest semantics,
  but the digest is produced by streaming JSON without a whole-graph deep copy.
- Timing diagnostics are optional evidence. Loss of a detached stdout pipe may
  not change geometry or audit status.
