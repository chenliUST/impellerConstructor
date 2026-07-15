# Known Limitations

1. The source STEP remains the only B-Rep authority. The browser displays a recorded source tessellation, not the original analytic faces.
2. The V1.1.2 reconstruction is a sampled review surface graph. It is not a stitched, watertight or independently certified CAD solid.
3. Exact source B-Rep collision was not evaluated. Topology separation is measured, while collision remains explicitly `UNKNOWN`.
4. The reconstructed UV-sample collision check passed, but it cannot replace an exact B-Rep interference test and cannot promote the candidate.
5. The frozen V1.1.2 representation does not preserve the source face identities, local holes, manufacturing details or all source spline degrees of freedom.
6. Camber, normal thickness, edge-curve and periodicity objectives failed. No accepted regional-deviation section is emitted for this rejected candidate.
7. Deviation is an unsigned bounded mesh-sample comparison. It is not certified dimensional metrology and cannot establish tolerance compliance.
8. Periodic phase alignment rotates about the confirmed axis only; it does not fit translation or scale.
9. The reconstructed surface graph is open, so its signed mesh volume is not comparable to the source solid volume.
10. Screenshots supplement the machine-readable audit and are not acceptance evidence by themselves.
