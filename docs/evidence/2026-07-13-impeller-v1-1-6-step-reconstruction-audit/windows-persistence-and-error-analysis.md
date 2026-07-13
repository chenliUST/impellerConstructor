# V1.1.6 Windows Persistence Incident And Reconstruction Error Analysis

Date: 2026-07-13

## Persistence incident

Failed audit `step-audit-7b3aa65ea142462e` stopped after frame resolution with
`WinError 5` while replacing `status.json.tmp` with `status.json`. The audit
directory ACL granted the current user full control. The failure handler then
successfully replaced the same destination with the terminal FAILED status.
This proves a transient Windows sharing/scan lock rather than a durable access
control failure.

The previous writer also reused one fixed `status.json.tmp` name. The corrected
writer uses a unique same-directory temporary file for every update, flushes and
fsyncs it, retries `PermissionError` 12 times with bounded backoff, removes the
temporary file, and reports `v116_audit_persistence_failed` rather than a STEP
parse failure if the lock persists.

Pressure verification uploaded the supplied 5.6 MiB STEP through HTTP and polled
status every 50 ms. Audit `step-audit-167ac48d89bd4c59` completed all ten stages
after 463 status reads without a persistence failure.

## Comparison frame correction

The source axis was already exact, but rotation about that axis remained an
undefined gauge freedom. The former comparison used zero phase and therefore
counted a source/reconstruction zero-angle difference as shape error.

The corrected primary comparison searches exactly one 13-blade pitch and permits
only rotation about the confirmed axis. It applies no translation, scale fit or
free ICP. The accepted audit recorded:

| Quantity | Value |
| --- | ---: |
| Periodic phase | +10.432692 deg |
| Bounded phase objective before | 3.892426 mm RMS |
| Bounded phase objective after | 2.974975 mm RMS |
| Objective improvement | 23.5702% |
| Full bidirectional RMS before correction | 2.720300 mm |
| Full bidirectional RMS after correction | 2.110076 mm |
| Full P95 before correction | 5.728954 mm |
| Full P95 after correction | 4.819965 mm |

## Remaining error causes

The remaining error is not primarily a hub-profile fit failure. The six-control
hub and tip profile fits have RMS residuals of 0.109318 mm and 0.064853 mm.

The dominant remaining losses are:

1. The source is one closed 240-face B-Rep solid; V1.1.2 reconstructs an open
   84-surface review graph. Signed volume and closed-solid topology are not
   comparable.
2. The source contains 150 exact B-spline face identities. V1.1.2 reduces the
   blades to five span stations and its existing skeleton/thickness/cap fields,
   so local section and spanwise detail cannot be represented exactly.
3. Auxiliary and stepped cylindrical holes, local edge treatments and exact
   source face identity are explicitly unsupported. Source radius reaches
   4.2 mm while the reconstructed main bore stops at 7.9 mm.
4. The source axial range is -6.5503 to 29.9497 mm; reconstruction is -5.75 to
   25.0593 mm. The upper source boss/material detail is therefore absent from the
   reconstructed envelope.
5. Semantic classification remains uncertain for 110 of 240 faces: 97
   `other_material` faces at confidence 0.45 and 13 trailing-edge candidates at
   confidence 0.58. Eleven mapped scalar parameters have mapping confidence
   below 0.70, concentrated in lean, edge radii, sweep and root treatment.
6. Deviation is unsigned triangle-sample distance. It is a review diagnostic,
   not exact face-to-face OCCT metrology, and currently reports one aggregate
   reconstruction role because source/reconstruction face identity is not
   preserved.

After phase correction, source-to-reconstruction RMS is 1.968709 mm and
reconstruction-to-source RMS is 2.306616 mm. The larger reverse value is
consistent with extra/open reconstructed transition surfaces and topology that
does not correspond one-to-one with source exterior faces.

## Required next geometry work

Do not reduce the residual through unconstrained ICP. The next geometry-focused
work should first improve source face-role classification and exterior-face
matching, then fit the five source section loops directly into the existing
V1.1 fields with per-station residuals. Features outside the V1.1.2 language must
remain explicit unsupported deltas until the V1.2 geometry contract is ready.
