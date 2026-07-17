# Impeller V1.1.6 R8 Insight Log

Date: 2026-07-16

## Findings

### Mirrored geometry was an authority problem

The apparent mirrored shroud-like surface was not solved by a render transform.
The reconstruction path allowed support orientation to be inferred from a
compressed profile without proving that blade evidence lay between the measured
hub and tip. The correction is an ordered hub-tip correspondence and an explicit
material-domain projection gate.

### One tip edge was insufficient

The KS007G23B open tip cap shares different streamwise boundaries with the two
blade sides. Selecting only the longest boundary shifted the inferred inlet by
approximately 0.87 mm. Both side chains are topology evidence; neither is a
display duplicate.

### Nose geometry needs bounded branch handling

The pressure-side tip boundary has one small radial turn when projected into
`(R,Z)`. Individual increments were smaller than source tolerance, but their
cumulative displacement was significant. A deadband turning-point detector is
therefore required. It may split one turn and retain provenance; multiple turns
remain ambiguous.

### Compressed controls cannot certify source containment

Six controls are appropriate for the V1.1.2 reduction, but they lose local
source envelope detail. Source topology, accepted samples, and residuals must
remain available independently of the reduced parameter payload.

### Positivity should be structural

Sampling a scalar field densely is evidence, not a proof. With positive rational
weights, positive control coefficients provide a global positive lower bound.
This is both stronger and independent of review mesh density.

### Global nearest-mesh error was misleading

The old metric mixed supported surfaces with the keyway, auxiliary holes,
bottom/boss geometry, and unrelated closures. It could neither diagnose a blade
side nor compare fairly after exclusions changed. Corresponding semantic roles
and directional distributions are now the primary review evidence.

### Labels must match the numerical primitive

Triangle-centroid and vertex-nearest distances cannot be called distance to a
source face. R9 evaluates points against triangle interiors and edges. Radius
buckets and a centroid-radius lower bound accelerate the exact tessellated
surface query without changing the selected nearest triangle.

### Scope completeness is topological

A partition can account for every source face while excluding every blade.
Comparison readiness therefore requires hub, blade side, attachment, and
topology-specific tip/shroud roles plus the expected periodic instance count.

### Directional normalization is part of metric identity

Concatenating forward and reverse samples silently weights the direction with
more triangles. R10 treats each direction as an independent distribution and
then applies fixed equal weights. This makes the symmetric summary invariant to
unequal directional tessellation counts.

### Periodicity is not permission for cross-instance nearest matching

Family-level blade regions allowed a reconstructed blade to match a neighboring
source instance. R10 binds side, root, and tip comparisons to the measured
periodic instance. Pressure/suction remain an instance material-boundary union
until face-level side identity is independently authenticated.

### Global phase does not establish instance identity

A correct one-pitch phase rotation can still leave source instance zero paired
with generated instance one. R11 therefore resolves one cyclic lattice offset
per population after applying the global phase. Instance-level deviation is
measured only after this second identity step.

### Cache identity must be transitive

Artifact hashes and a manifest digest are insufficient if a stale status file
can name a different source or audit. Reuse now requires the directory, status,
manifest, source SHA-256, revision, manifest digest, and artifact digests to form
one consistent identity chain.

### Partial ownership cannot reuse a full-population modulus

A cyclic shift measured from all blade sides cannot be reduced modulo only the
recognized subset of leading or trailing faces. R12 admits a periodic role to
instance metrics only with complete authenticated population coverage; partial
edge ownership remains explicit excluded evidence.

### Aggregate blade count does not prove population identity

A four-instance inventory can still be the wrong `3 main + 1 splitter` set for
an authenticated `2 main + 2 splitter` contract. Population count, exact
instance membership, and lattice indexes must agree independently. Edge closure
coverage is also population-specific: incomplete splitter evidence must not
discard a complete main population.

### Visualization must consume geometry authority

The prior STL pane exposed tessellation edges as visually noisy lines and could
not show NURBS parameterization. A Geometric Manifest generated from the same
surface graph provides translucent faces and true UV curves while retaining a
clear review-grade label.

## Remaining Risks

- The frozen V1.1.2 preset path remains a five-station contract. The separately
  labeled R8 adaptive review variant can consume 5 to 9 approved stations, but
  pose, camber, edge, thickness, or periodic mapping terms may still be rejected.
- Corresponding deviation is sampled and unsigned, not exact CAD metrology.
- Point-to-triangle evidence is exact for the retained tessellation, but it is
  still tolerance-dependent and is not an exact B-Rep closest-point result.
- Closed shrouds represented by several disconnected material patches need
  explicit grouped support ownership before promotion.
- Source LE/TE closure faces that overlap root/tip topology remain unresolved.
  Their exclusion is explicit and forces `PARTIAL_REVIEW`; complete LE/TE
  correspondence requires a future source-face trimming/ownership contract.
- Main/splitter adaptive scalar fields require separate population authorities.
  R10 rejects splitter adaptive reuse instead of applying the main field.
