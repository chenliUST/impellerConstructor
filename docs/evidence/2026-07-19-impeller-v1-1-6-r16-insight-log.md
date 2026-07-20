# Impeller V1.1.6 R16 Insight Log

Date: 2026-07-19

## Root Cause

1. The recovered STEP section curves were substantially closer to the source
   blade than the generated blade surfaces, but they were not the constructor
   authority.
2. The old mapping discarded physical meridional curve coordinates, retained
   normalized sample fractions, and independently stretched every station to
   the complete support interval. This changed both the physical chord range
   and span-dependent endpoint position.
3. Pressure and suction endpoints were then forced onto common streamwise
   endpoints. The measured PS/SS leading stagger was lost before any surface
   was lofted.
4. The scalar constructor rebuilt side curves as camber plus or minus a
   Q-only thickness offset. A real three-dimensional pressure/suction pair is
   not generally representable by that operation, especially near a swept and
   leaned leading edge.
5. The downstream loft correctly interpolated invalid rows. The resulting
   blade becoming nearly vertical at the leading edge was therefore not a
   renderer defect or an isolated edge-bulge defect; it was a coordinate and
   geometry-authority failure upstream of meshing.
6. One global active-root fraction was inferred from the minimum support
   separation and applied over the whole chord. Hub, root attachment, and blade
   surfaces consequently shared an artificial boundary height, explaining why
   apparently unrelated faces looked cut at the same Z level.
7. The blue and red overlays mixed three different meanings: source curves,
   curves transformed with incomplete frame provenance, and generated-loop
   proxies. A curve could look plausible while being displaced, shortened, or
   unrelated to the rendered surface.
8. Later comparison preprocessing amplified the cost of diagnosis by copying
   and retriangulating the complete dense surface graph for every region and
   every surface. That was a performance defect, not a geometry defect, but it
   made full-fidelity validation impractically slow and memory-heavy.
9. The direct builder correctly marked sharp LE/TE placeholders as
   nonmaterial, but pattern decoration later rewrote all blade surfaces as
   material. That resurrected obsolete bridge faces in the STL, manifest and
   heatmap and produced large false edge errors.
10. A topology-only tip heuristic treated every non-support closure adjacent
    to both blade sides as a tip patch. On multi-patch STEP blades that set also
    contains leading and trailing closures; source semantic roles must own this
    partition.
11. Comparing each reconstructed subpatch independently to the complete source
    semantic region duplicates reverse samples and inflates aggregate error.
    The mathematically valid pair is source region versus union of all material
    patches assigned to that region.

## Design Conclusions

- Physical coordinates, local NURBS parameters, and display parameters have
  different semantics and must never reuse one field name or normalization.
- A STEP reconstruction should interpolate authenticated measured curves
  directly. Compact camber/thickness/pose fields are valuable derived design
  parameters, but they cannot silently replace geometry during reverse
  engineering.
- If the same STEP supplies the complete trimmed rational B-spline side face,
  re-lofting its section curves in a chosen UV correspondence is unnecessary
  and can create crossings. The stronger authority is the trimmed source face,
  with every recovered section required to be analytically incident within the
  source tolerance.
- Active root and tip positions are fields over streamwise position. A single
  lift ratio can be a preset convenience, not a universal reconstruction rule.
- Pressure and suction sides need independent endpoint witnesses. Shared
  topology is expressed at an actual seam or edge surface, not by collapsing
  distinct physical endpoints.
- Closure construction must follow source topology. A sharp seam, a rounded
  measured closure, and a finite edge face are different geometric contracts.
- Root and tip patches require trim-aware sampling. Sampling an entire
  underlying source NURBS face can generate large nonmaterial wings even when
  the face equation itself is exact.
- Visual overlays are evidence only when source and generated curves have
  explicit authority, frame, station, and surface-intersection provenance.
- Collision checks must operate on material topology. Diagnostic seam
  placeholders are useful for inspection but cannot be counted as physical
  interpenetration.
- Performance evidence needs its own stages. Combining preprocessing with
  deviation timing hides the actual bottleneck and makes optimization claims
  unverifiable.

## Implementation Lessons

- The direct curve network is an opt-in V1.1.6 reconstruction patch, so the
  repair does not rewrite historical preset semantics.
- Degree compatibility and bounded smoothing are allowed between measured
  stations, but authoritative station curves may not move.
- Material UV surfaces are now triangulated once into shared indexed arrays.
  Region and per-surface comparison reuse those arrays, avoiding repeated
  Python triangle-record allocation and whole-graph copies.
- Intermediate region and mesh caches are released as soon as their aligned
  descendants are produced. Peak working set is captured in audit evidence so
  memory reduction can be measured rather than inferred.

## Remaining Maturity Boundary

- R16 is sampled review-grade reconstruction. Exact OCCT analytic surface
  identity and certified B-Rep sewing remain out of scope.
- The direct network can expose source geometry that the current parametric
  V1.1.2 design language cannot yet edit without loss. Such cases must remain
  explicit rather than being coerced into the old scalar fields.
- Unsupported spline, hole, keyway, bore, and bottom-boss features remain out
  of the comparison acceptance scope until their construction semantics are
  defined.

## R16.23 Hub Support Union Insight

1. The red hub sector was not evidence that the fitted hub profile was
   non-axisymmetric. The selected hub patch `source_face_00055` had an adjacent
   profile-conformant complement, `source_face_00056`; their combined area was
   consistent with the neighboring passage patches.
2. Coarse periodic connected-component ownership is not authoritative for a
   support split. In the real source, `source_face_00056` belonged to a
   neighboring blade component even though its exact topological neighbor was
   the hub patch owned by `main_instance_0007`. Support adjacency therefore
   has priority when assigning a complementary face to a periodic pitch.
3. Meridional sampling paths cannot define circumferential coverage. Their UV
   direction is selected for profile recovery and may flip when trace counts
   change. Coverage now uses canonical coordinates sampled from exact trimmed
   vertices and edges, while meridional paths remain dedicated to profile fit.
4. A preliminary hub fit is permitted only as a candidate-recognition aid. It
   is unauthenticated and cannot become the final semantic partition. After
   union selection, the pipeline creates one immutable face partition and
   recomputes the authenticated hub fit from all promoted source faces.
5. Profile conformance alone is insufficient because a root fillet can lie
   near the hub. A candidate adjacent to both an initial hub patch and an
   authenticated blade side is therefore protected as root attachment
   geometry before residual ranking. Promotion additionally requires direct
   initial-hub adjacency, compatible surface type, one unambiguous support
   owner, ownership of a deficient pitch, and positive angular coverage gain.
6. The real source also exposed `source_face_00134` as a second small
   profile-conformant complement. Treating the issue as a hard-coded exception
   for face 56 would therefore leave the semantic ledger incomplete.
7. Population-relative normalization is not a 360-degree coverage proof. If
   every pitch exposes the same tiny angle, each ratio equals one. The coverage
   contract must combine an absolute pitch-angle floor with the relative
   population floor and require every expected instance to satisfy both.
8. Reclassification alone does not remove a promoted face from a previously
   formed periodic connected component. Downstream representative instances
   now preserve coarse provenance separately while excluding material support
   ids from blade, root-attachment, tip, and section construction domains.
9. Exact trimmed boundary evidence cannot silently fall back to a subset of
   readable edges. One failed edge sample invalidates that face's angular
   coverage evidence and triggers the stable fail-closed reason.
10. Main and splitter counts are independent periodic authorities. Dividing
    360 degrees by their summed count weakens both absolute gates and can hide
    an incomplete population. Hub support evidence therefore carries an exact
    population-to-instance partition and computes each median and pitch within
    that partition.
11. A shared support face is not proof of full circumferential support merely
    because it touches every blade. Its exact trimmed-boundary union must pass
    an absolute full-revolution gate; this path does not require an unrelated
    preliminary meridional fit when no complement is being ranked.
12. Filtering only the selected representative leaves promoted support faces
    in the trusted full-population partition. Pattern validation then observes
    contradictory periodic and material ownership. The full authoritative
    population payload must be sanitized while preserving the coarse payload
    under a separate provenance key.

## R16.24 Attachment Patch And Performance Insights

1. A trim polygon partition is not automatically a source-boundary partition.
   Its internal diagonals can geometrically coincide with another patch while
   having no STEP edge authority. Shared-edge identity must be assigned after
   testing each subpatch edge against the ordered source trim path.
2. Position continuity cannot establish differential continuity. The real
   audit contains source edges with sub-micron coordinate gaps and nearly
   90-degree normal changes. These are source sharp edges, not sewing gaps and
   not G1/G2 transitions.
3. Endpoint corners require independent evidence. An edge can have a stable
   interior tangent plane while the endpoint curvature proxy diverges. Folding
   corner metrics into one interior maximum hides exactly the spike that visual
   review is intended to expose.
4. The topology bottleneck was candidate enumeration, not the final strict
   matcher. Spatial and semantic indexing reduced millions of possible pairs
   while preserving the exact final gap and source-identity checks.
5. Dense Python geometry graphs are dominated by nested point arrays. Copying
   the complete graph to change a handful of surface flags doubled memory and
   made parameter inspection appear to be a geometry bottleneck. Copy-on-write
   records preserve isolation without cloning immutable samples.
6. A deterministic generation id does not require constructing one giant JSON
   byte string. `JSONEncoder.iterencode` preserves the previous byte semantics
   while bounding transient memory.
7. Diagnostic telemetry must be fail-open. A detached Windows stdout pipe can
   raise `OSError(22)`; allowing that exception to escape mislabeled a healthy
   reconstruction as a STEP parse failure.
8. Periodic normalization removed 112 exact-distance queries relative to the
   legacy count while still recomputing rejected aliases. This is a measured
   optimization, not an assumption that every nominally periodic source face
   is equivalent.
9. R16.24 still spends about 93 seconds recomputing the generation digest in
   independent validation and about 109.5 seconds on hub material closure
   deviation. Future work may remove a duplicate validation only when the same
   graph identity and passing report are carried as explicit evidence; it may
   not simply trust a stale id.
