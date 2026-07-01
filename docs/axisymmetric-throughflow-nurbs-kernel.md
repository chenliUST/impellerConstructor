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
- Strength, DFMA, and manufacturability constraints are not part of this kernel yet. CFD support starts in v0.4 as a manifest-level patch contract, not as a solver or mesh adapter.

## v0.4 Surface/Feature Graph Contract

The v0.4 DSL promotes the sampled NURBS kernel into a stable surface and feature graph contract. The CAD review view is a full 360 degree surface graph with deterministic surface ids, named boundary curves, and construction lines that are suitable for human inspection and regression testing. Numeric design parameter changes may move sampled points, but they must not rename the review surfaces, boundary semantics, or CFD patch group contract inside the same campaign.

The feature graph separates reviewable geometry from simulation intent. It labels blade pressure and suction surfaces, hub and tip or shroud walls, inlet and outlet boundaries, blade transition regions, assembly features, and schema-only tuning features. Internal assembly features such as mounting bores, shaft seats, keyways, balance holes, grooves, and lightening slots remain available for CAD review where relevant, but the CFD view can suppress them without changing the core throughflow wetted-surface contract.

The `cfd_full_360` simulation manifest is the first CFD target for v0.4. It describes a full 360 wetted-surface domain rather than a periodic sector, and it publishes required patch groups with stable group ids and instance ids. The required groups cover inlet and outlet patches, hub wall, tip or shroud wall, blade pressure and suction walls, leading and trailing edge walls, and sampled root/tip transition walls. This lets downstream mesh and solver adapters bind to semantic patch groups before exact industrial B-Rep sewing is available.

Fillet, blend, and transition labels in v0.4 are research-grade sampled semantics. `root_fillet_wall`, `tip_fillet_wall`, `leading_edge_wall`, and `trailing_edge_wall` identify sampled transition regions and closure surfaces; they do not yet guarantee exact variable-radius fillets, watertight OCCT blends, or production mesh-quality curvature control. Those labels are intentionally stable so validation, optimization, and future CAD-kernel upgrades can preserve the same external contract while improving the underlying geometry.

