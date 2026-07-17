# Impeller V1.1.6 R13 Semantic Change Log

Date: 2026-07-17

## Authority Boundary

- V1.1.2 remains the frozen universal geometry contract.
- R13 behavior is selected only by
  `v116_adaptive_step_reconstruction_extension` and remains review-grade.
- Uploaded STEP B-Rep remains measurement authority. Sampled reconstruction,
  heatmap, and Geometric Manifest artifacts are not certified CAD metrology.

## Changed Semantics

1. `source_support_span_mapping` records measurement-station provenance. It is
   not construction authority unless a future contract explicitly declares
   `constructor_span_authority`.
2. Root and tip active offsets continue to use local streamwise attachment
   fields. A global maximum lift divided by the minimum support gap may not
   displace every section station.
3. Adaptive minimum thickness is a measured/fitted positive NURBS control-hull
   bound and remains adjustable. It is not a universal hardcoded minimum.
   Ordinary V1.1.2 metrics retain their historical control-net minimum.
4. Source cap records are construction targets only when explicitly marked as
   authenticated direct curves and represented by degree-3-or-higher NURBS.
   Synthetic degree-1 section closure chords remain measurement provenance and
   cannot be presented as measured LE/TE construction authority.
5. A V1.1.6 root footprint that reaches `s=0` or `s=1` intersects the support
   boundary in the metric S-Q domain. It is not silently clamped after 3D
   mapping and is not normally extrapolated beyond the authenticated hub
   profile.
6. Root LE/TE footprint segments are reparameterized by arc length after
   support-boundary intersection. This preserves a smooth cap while preventing
   near-zero mesh cells at cap extrema.
7. Complete hub-passage ownership is detected across compatible singleton area
   groups. One-to-one periodic matching is required even when adjacent passage
   patches have slightly different areas.
8. The reconstruction surface ledger inventories every material surface. A
   missing or malformed `uv_grid` is `FAILED_UNRESOLVED`, never silently absent.
9. Every evaluated reconstruction surface has an individual heatmap region.
   Unsupported shaft-interface/mounting-bore geometry remains neutral and
   contributes zero deviation samples.
10. R13 contract ids are versioned as:
    - `impeller_v1_1_6_corresponding_surface_deviation_v5`;
    - `impeller_v1_1_6_deviation_heatmap_v2`;
    - `impeller_v1_1_6_geometric_manifest_v2`;
    - `impeller_v1_1_6_supported_surface_comparison_scope_v6`.

## Compatibility

- Legacy V1.1.2 construction still clamps out-of-domain support parameters and
  does not consume the adaptive attachment or cap contracts.
- R13 uses implementation revision `axis_first_triangle_surface_r13_2`, so R12,
  R13, and R13.1 caches are not reusable as R13.2 evidence.
- Existing STEP audit endpoints and artifact names remain stable.

## Maturity

R13 remains `review_only_not_promotable`. Source PS/SS identity, exact LE/TE
ownership, unsupported local hub-feature masks, and exact B-Rep distance are not
yet sufficient for certification.
