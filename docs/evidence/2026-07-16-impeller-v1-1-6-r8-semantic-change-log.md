# Impeller V1.1.6 R8 Semantic Change Log

Date: 2026-07-16

## Authority Boundary

- Uploaded STEP B-Rep remains the source measurement authority.
- V1.1.2 remains the frozen base geometry contract.
- Adaptive reconstruction is separately identified as
  `v1.1.6_adaptive_review_extension_r1` and remains review-only.
- No proxy mesh, display artifact, or sampled field is promoted as certified
  B-Rep metrology.

## Changed Semantics

1. Open tip reference evidence now includes every exact cap-to-side shared edge
   chain for both authenticated blade sides. The former longest-edge-only rule
   is removed.
2. A single tolerance-qualified radial turn in a projected support edge is
   decomposed into ordered branches. Multiple turns fail closed.
3. Hub and tip/shroud profiles form an ordered meridional support strip.
   Representative blade evidence must project into that strip; mirrored or
   opposite-side fallback geometry is forbidden.
4. Authenticated pressure/suction side roles take precedence over hub adjacency.
   A side touching the hub is not automatically reclassified as root attachment.
5. Thickness, root width, and root lift are adaptive rational NURBS scalar
   fields. Positivity is proven by positive weights and positive control
   coefficients; no hardcoded review minimum is inserted.
6. The comparison scope is role-to-role. Supported surfaces contribute only to
   their corresponding source/reconstruction family.
7. Keyways, auxiliary holes, unsupported nonplanar bottom/boss faces, balancing
   details, and unresolved closures are explicit exclusions.
8. Deviation reports two directional distributions plus a symmetric combined
   sample distribution. A directional heatmap is not called bidirectional.
9. The reconstruction review artifact is a generation-bound Geometric Manifest
   with translucent surface shading and real UV curves.
10. Legacy global metrics are recorded as non-comparable. R8 acceptance begins
    at `NOT_EVALUATED` until a corresponding-surface baseline is approved.
11. Post-review R9 evidence measures reconstruction samples to tessellated
    triangle interiors/edges, not to triangle centroids or vertices. The
    R10 contract id is `impeller_v1_1_6_corresponding_surface_deviation_v4`.
12. A comparison partition is complete only when topology-required roles and
    every expected periodic blade instance are present. Merely assigning every
    source face to included/excluded scope is insufficient.
13. A completed rejected review audit may be reused without becoming
    promotable, provided implementation revisions and all artifact hashes
    match. Review completion and geometry acceptance remain separate states.
14. Symmetric statistics use independently normalized directions with fixed
    `0.5/0.5` weights; unequal tessellation counts cannot change directional
    authority.
15. Periodic blade regions are compared per source instance. Unresolved LE/TE
    ownership yields `PARTIAL_REVIEW`, not comparison-scope `PASS`.
16. A main-population adaptive field is never reused for a splitter. Reusable
    audit status additionally binds the canonical manifest SHA-256.
17. Global periodic phase and periodic instance identity are distinct. R11
    applies one post-phase cyclic lattice assignment per population before
    corresponding-surface measurement.
18. Cache identity is transitive across audit directory, status, manifest,
    source SHA-256, manifest digest, implementation revision, and artifact
    digests.
19. An empty declared splitter family is not equivalent to no splitter family;
    it is rejected until splitter-specific fields exist.
20. Triangle-centroid directional summaries and vertex-interpolated heatmap
    values are labeled separately in the frontend.
21. R12 binds instance correspondence to authenticated pattern-population
    `lattice_index` evidence. Instance-name ordering is not production
    authority.
22. A partially covered LE/TE role contributes no instance metric. Its faces
    are explicit unresolved-closure exclusions and retain `PARTIAL_REVIEW`.
23. Authenticated population membership is exact, not count-only. Each
    population count, instance set, and contiguous lattice index set is
    validated independently; partial LE/TE exclusions are population-specific.

## Compatibility

- Historical V1.1.2 parameter defaults retain their legacy values and hashes.
- Existing STEP upload, persistence, and artifact endpoints remain available.
- Cache compatibility is invalidated by implementation revision
  `axis_first_triangle_surface_r12`.
- Legacy audits without a declared Geometric Manifest may use STL display;
  audits declaring the artifact fail visibly when it is unavailable.

## Explicit Non-Goals

- Reconstructing the source keyway, three auxiliary holes, bottom boss, or
  nonplanar bottom in V1.1.2.
- Promoting sampled deviation to exact signed B-Rep distance.
- Changing the V1.2 engineering-solid development line.
- Claiming a passing reconstruction when V1.1.2 mapping terms remain outside
  their measured gates.
