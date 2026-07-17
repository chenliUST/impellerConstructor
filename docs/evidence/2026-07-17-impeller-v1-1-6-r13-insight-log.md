# Impeller V1.1.6 R13 Insight Log

Date: 2026-07-17

## Measurement Coordinates Are Not Construction Offsets

The recovered station interval `[0.3411, 0.9761]` describes where STEP section
evidence was measured. Treating it as the active blade span globally displaced
the complete blade family and made the root appear too wide. Construction must
consume local lift and width fields independently of measurement station
provenance.

## A Closure Polyline Is Not a Measured Edge Curve

The source section records contained authenticated pressure and suction side
curves, while the apparent LE/TE records were synthetic segments used only to
close a sampled loop. Promoting those degree-1 chords to constructor targets
created visible edge bumps. A direct cap curve requires independent topology,
degree, endpoint-frame, and provenance evidence.

## Clamp And Extrapolate Are Both Incomplete Answers

Clamping root footprint parameters after the S-Q offset collapsed several
different samples to one support endpoint. Unbounded tangent extrapolation
removed the collapse but placed the footprint outside authenticated hub
material. The bounded construction is an explicit metric-domain intersection
with the support boundary, with tangent extrapolation retained only as a safety
fallback for direct mapper calls.

## Smooth Geometry Can Still Have Bad Parameterization

After the support-boundary correction, one triangle per blade remained near
degenerate. The curve itself was continuous; uniform parameter sampling placed
two points only about `0.00072 mm` apart at a cap extremum. Arc-length
reparameterization increased the first-blade minimum root cell area from about
`1.85e-9` to `1.17e-6 mm^2` without changing the support authority.

## Face Coverage And Face Correspondence Are Different Claims

R13.1 colored every evaluated reconstructed surface, but pressure and suction
still compare to a shared per-instance source material-boundary union, and hub
closure faces use a review-only material-component union. This proves complete
display coverage, not unique source-face identity. The algorithm remains
rejected until those correspondences are independently authenticated.

## Unsupported Features Must Remain Visible But Numerically Silent

The splined shaft interface, nominal bore, three auxiliary holes, and
unsupported bottom/boss features should not disappear from review. They remain
neutral geometry with explicit `NOT_EVALUATED` state and contribute no samples
to aggregate deviation.
