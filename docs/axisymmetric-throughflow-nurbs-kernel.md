# Axisymmetric Throughflow NURBS Impeller Kernel

This kernel covers the current open and closed radial throughflow impeller study cases.
It is intentionally narrower than the whole impeller taxonomy.

## Construction Order

1. Establish the coordinate system: the shaft is the Z axis, and all hub/tip profiles are defined in the R-Z meridional plane.
2. Define the hub profile as a clamped cubic NURBS curve from the top eye small radius to the bottom backplate large radius.
3. Revolve the hub profile around Z to create the blade root attachment surface.
4. Add hub solid support surfaces: the bottom annular face and the mounting-bore cylinder.
5. Define the tip or shroud profile as a second clamped cubic NURBS curve above the hub profile.
6. Revolve the tip profile to create either an open tip reference surface or a closed shroud surface.
7. For each blade instance, sample conformal root and tip curves from the hub/tip surfaces.
8. Build the blade mean surface between root and tip.
9. Offset the mean surface circumferentially to create pressure and suction surfaces.
10. Add four blade closure surfaces: leading edge, trailing edge, root closure, and tip closure.
11. Emit shaded surfaces and construction lines from the same surface graph.

## Current Scope

- The hub orientation is explicit: `u=0` is the top eye small radius, and `u=1` is the bottom backplate large radius.
- Blade edge closure surfaces are ruled surfaces. They close the sampled topology but are not yet engineered variable-radius fillets.
- The exported CAD path remains research-grade. Strict OCCT-style manifold sewing and healing is a later step.
- CFD, strength, DFMA, and manufacturability constraints are not part of this kernel yet.

