# V1.1.6 Known Limitations

- The uploaded STEP B-Rep is authoritative. Source and reconstructed display
  artifacts are tessellations with recorded tolerance.
- The V1.1.2 constructor cannot retain exact source B-spline face identity,
  stepped spline-bore details, three auxiliary holes, balancing details, local
  cones/tori, tolerances or manufacturing semantics.
- Pressure/suction assignment remains orientation-neutral when aerodynamic flow
  evidence is insufficient. The audit reports `blade_side_a/b` instead of making
  an unsupported physical claim.
- Generic support-profile extraction uses bounded envelope evidence. A known
  source SHA may reuse previously recorded source measurements as fit targets,
  but the six NURBS controls are still solved by constrained least squares.
- Primary comparison uses only the recorded rigid source-to-canonical transform.
  No scale or primary ICP fit is allowed. Signed distance is not claimed for the
  open sampled reconstruction.
- Distances are nearest mesh-sample diagnostics, not exact point-to-B-Rep
  metrology. High local values can include tessellation and semantic reduction
  error.
- Semantic deviation currently reports complete reconstruction-triangle coverage
  as one aggregate role. Per-source-role exact surface correspondence remains a
  future improvement.
- Assemblies, multiple solids, corrupt STEP repair, arbitrary turbomachinery and
  general-purpose reverse engineering remain out of scope.
