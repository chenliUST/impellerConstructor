# V1.1.6 Axis-First STEP Reconstruction Evidence

This directory records the final Task 12 review run against `KS007G23B.stp`.

## Scope

- Runtime release: `1.1.6`
- Canonical reconstruction geometry: `1.1.2`
- Algorithm revision: `axis_first_pattern_material_r6`
- Audit id: `step-audit-a7a5e88b539e41c5`
- Source SHA-256: `1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5`
- Source authority: STEP B-Rep
- Reconstruction maturity: review-grade sampled surface graph

The audit process completed successfully, but the reconstruction candidate was rejected by the geometry acceptance contract. `status: PASS` means that all audit stages produced evidence. It does not mean that the reconstructed geometry passed acceptance.

## Result

- Axis-first algorithm status: `REJECTED`
- Mapping status: `REJECTED_REVIEW_CANDIDATE`
- Disposition: `review_only_not_promotable`
- Acceptance contract: `ks007g23b_axis_first_acceptance_v1`
- Acceptance status: `REJECTED`
- Promotable: `false`
- Failed mapping terms: camber, normal thickness, edge curves, periodicity
- Periodic pattern status: `REVIEW_ONLY`
- Source topology: separated periodic components detected
- Source exact B-Rep collision: not checked (`UNKNOWN`)
- Reconstructed sampled UV collision: passed

The source exact-collision state is deliberately retained as unknown. The sampled reconstruction check cannot promote or certify the result.

## Deviation

| Metric | Actual | Acceptance maximum | Status |
| --- | ---: | ---: | --- |
| Bidirectional RMS | 2.608269 mm | 1.477053 mm | FAIL |
| Bidirectional P95 | 6.040549 mm | 3.373975 mm | FAIL |
| Top silhouette Hausdorff | 5.275920 mm | 3.152468 mm | FAIL |
| Meridional silhouette Hausdorff | 10.184372 mm | 6.101068 mm | FAIL |

Additional recorded values: median `0.896158 mm`, maximum `7.501618 mm`, and symmetric Chamfer distance `3.290790 mm`.

## Visual Evidence

- `full-workspace.png`: source, V1.1.2 reconstruction, heatmap and report in one view.
- `source-pane.png`: recorded tessellation of the source STEP B-Rep.
- `reconstruction-pane.png`: rejected review reconstruction.
- `heatmap-pane.png`: visible unsigned sampled mesh-distance heatmap excerpt.
- `report-pane.png`: global process, acceptance, promotability and collision-provenance states.

The screenshots are review aids. Machine-readable acceptance values come from the audit manifest and are summarized in `acceptance-summary.json`.

## Reproduction

The audit artifacts were generated under the local runtime root recorded in `verification.txt`. That temporary runtime is not the evidence authority; retained hashes identify the exact source and generated artifacts. See `known-limitations.md` before using this evidence.
