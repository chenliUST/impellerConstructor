# V1.1.6 Known Limitations

- The uploaded STEP B-Rep is authoritative. Source and reconstructed display
  artifacts are tessellations with recorded tolerance.
- The V1.1.2 constructor cannot retain exact source B-spline face identity,
  stepped spline-bore details, three auxiliary holes, balancing details, local
  cones/tori, tolerances or manufacturing semantics.
- Pressure/suction assignment remains orientation-neutral when aerodynamic flow
  evidence is insufficient. The audit reports `blade_side_a/b` instead of making
  an unsupported physical claim.
- Support-profile extraction uses authenticated OCCT face/edge evidence. The
  six NURBS controls remain a constrained V1.1.2 reduction and are not relabeled
  as exact source poles.
- Primary comparison uses only the recorded rigid source-to-canonical transform.
  No scale or primary ICP fit is allowed. Signed distance is not claimed for the
  open sampled reconstruction.
- Distances are point-to-triangle diagnostics on the retained tessellation, not
  exact point-to-B-Rep metrology. High local values can include tessellation and
  semantic reduction error.
- R8 deviation is corresponding-role sampled distance, not exact surface-to-
  surface B-Rep metrology. R10 binds periodic blade regions per instance, but
  pressure/suction remain an instance-level material-boundary union.
- R11 resolves one cyclic instance offset per population after the global phase
  search. This is a deterministic angular-centroid identity assignment on the
  retained tessellation, not exact source-face naming recovered from CAD design
  history.
- R12 authenticates each population count, exact instance membership, and
  contiguous lattice index set. This proves deterministic comparison identity;
  it does not recover original CAD feature names or design intent.
- Keyways, three auxiliary holes, unsupported nonplanar bottom/boss faces,
  balancing details, and unresolved closures are excluded from R8 metric
  contribution and retained as explicit unsupported evidence.
- Unresolved LE/TE source-face ownership forces `PARTIAL_REVIEW`; complete
  comparison coverage is not claimed. Edge exclusions are population-specific,
  and a measured main adaptive field is not reused for splitter geometry
  without a separate population authority.
- The legacy global nearest-mesh metrics are not comparable with R8
  corresponding-surface metrics because their source scope differs.
- Multi-patch closed shrouds require explicit grouped inner/outer material
  ownership. The current closed topology path is not promoted for arbitrary
  disconnected shroud patch sets.
- R13.2 inventories every reconstructed material surface and gives every
  evaluated surface its own heatmap membership. This is complete display
  coverage, not proof of unique source-face correspondence.
- The nominal mounting-bore cylinder is excluded with the spline-affected shaft
  interface. Its deviation status is `NOT_EVALUATED`, not zero error.
- Hub top, bottom and outer material closures remain review-only comparisons
  against a broad material-component union. Exact masks for auxiliary holes,
  spline grooves, nonplanar bottom and boss features remain incomplete.
- R13.2 root support-boundary intersection removes endpoint collapse and the
  full geometry probe has no triangle below `1e-8 mm^2`; this does not certify
  exact B-Rep continuity or manufacturing suitability.
- Minimum thickness is a positive measured/fitted adaptive input. It may be
  adjusted in V1.1.6 and is not a universal hardcoded impeller rule.
- Frontend WebGL tests use mocked rendering resources. Real-browser pixel and
  depth-buffer screenshot acceptance remains pending.
- Assemblies, multiple solids, corrupt STEP repair, arbitrary turbomachinery and
  general-purpose reverse engineering remain out of scope.
