# Impeller V1.1.6 R15 Insight Log

Date: 2026-07-17

## Root Cause

1. An analytic axis is an undirected line. Choosing the world-facing sign that
   appears visually convenient is not enough to define constructor semantics.
2. The R14 canonical frame assigned the large-radius backplate to positive Z.
   Support fitting remained numerically valid, but its ordered endpoints were
   opposite the V1.1.2 contract.
3. Mapping copied those controls without named endpoint validation. Adaptive
   hub closure then combined independent minimum/maximum R and Z values and
   emitted an outer wall spanning nearly the full meridional flowpath.
4. The blade six-face surfaces still existed; the oversized hub cylinder
   occluded them. This is why the reconstruction looked like a cylinder even
   though surface counts alone did not reveal a missing-blade failure.
5. Independently framing the three comparison panes made a translated or
   oversized result look deceptively aligned. A comparison tool must preserve
   one canonical world before visual inspection has evidential value.
6. The periodic medoid mixed pressure/suction surfaces with root and edge
   patches. One physical blade has an extra STEP face split, so point density
   from transition topology dominated a gate intended to select the principal
   blade shape. The 13 blade-side pairs agree within about 0.069 mm even though
   the mixed full-component residual reached 1.614 mm.
7. Bottom-material recovery repeated the same polarity mistake downstream by
   using `max(hub_control_z)` as the hub terminal. Under eye-positive Z that is
   the eye, not the backplate. Named endpoints must govern material-plane
   direction as well as support fitting and closure.

## Design Conclusions

- Radial-weighted asymmetry is useful evidence, not a universal semantic rule.
  Authenticated support endpoints are stronger when available; ambiguous
  geometry must fail rather than inherit a world-axis fallback.
- Ordered arrays are not sufficient authority for engineering roles. Endpoint
  names, source provenance, coordinates, confidence, and streamwise direction
  must travel together through fitting, mapping, construction, rendering, and
  acceptance.
- Material closure must be derived from the same endpoint authority as the
  support surface. Recomputing roles from extrema inside a downstream builder
  creates a second, conflicting geometry authority.
- Representative selection and transition reconstruction need different
  evidence scopes. The blade-side pair selects periodic principal geometry;
  the complete component topology remains authoritative for root/edge closure
  and must not be discarded or averaged into the side-fit gate.
- Process completion and geometry acceptance are orthogonal. `COMPLETE` means
  the audit produced inspectable evidence; it does not mean the reconstructed
  geometry passed its residual or topology gates.
- Surface inventory and aggregate heatmap statistics cannot replace visual
  inspection. Occlusion, phase, truncation, and endpoint failures need common
  coordinates and role-specific evidence.

## Performance Observation

The representative exact STEP regression spends about three minutes building
the measurement bundle and about two minutes in bounded V1.1.2 review mapping.
The previous regression invoked the strict solver and then invoked the review
wrapper, which repeated the same strict solve. R15 keeps the same production
algorithm but removes that duplicate computation from the test while retaining
the rejection-reason assertion.

## Fresh Audit Observation

The R15.3 audit confirms that correcting a gross construction semantic does
not imply that the parameterization is accepted. The oversized cylinder is
gone and reconstruction-to-source P95 drops from 10.802 mm to 7.238 mm, but
source-to-reconstruction P95 rises from 46.662 mm to 53.430 mm and the
leading-edge reconstruction family remains near 18.189 mm P95. The evidence
therefore supports a narrow conclusion: R15 repairs axial polarity, closure,
and comparison-frame truthfulness; it does not solve V1.1.2 blade recovery.

The exact comparison also exposes a performance concentration. Four supported
hub-material surfaces account for the longest individual queries, with the
outer wall alone taking about 1,036.8 seconds. Future performance work should
split authenticated source material regions more narrowly before changing
distance mathematics or lowering sampling density.

## Deferred Work

- R15 does not add the unsupported spline, auxiliary holes, keyway, or source
  bottom-boss geometry.
- R15 does not redesign blade mathematics or loosen V1.1.2 residual gates.
- Further parameter-extraction and artifact-serialization performance work is
  separate from the R15 correctness repair.
