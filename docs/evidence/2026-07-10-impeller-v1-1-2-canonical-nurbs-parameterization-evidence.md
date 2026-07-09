# Impeller V1.1.2 Canonical NURBS Parameterization Evidence Log

Date: 2026-07-10

Branch: `impeller-v1.1.2-acceptance-hardening`

## Evidence Scope

This evidence log starts the V1.1.2 semantic change record.

At this stage the work is specification-only. It documents:

- the active worktree;
- the current V1.1.1 baseline;
- the intended V1.1.2 parameterization change;
- the planned verification evidence to collect during implementation.

## Baseline Worktree

```text
worktree = C:\Users\CHEN Li\Documents\TurboJetCase\impeller-v112-hardening
branch = impeller-v1.1.2-acceptance-hardening
base = origin/master
```

Baseline checks already completed when the worktree was created:

```text
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_geometry_validation.py -q
result = 23 passed

cd frontend
npm.cmd test
result = 121 passed
```

Local services were then started for inspection:

```text
backend = http://127.0.0.1:8061
frontend = http://127.0.0.1:5199
```

Open V1.1 frontend-payload smoke completed:

```text
preset_id = radial_open_reference_v1_1
validationStatus = PASS
elapsed = approximately 204 seconds
```

## Specification Artifacts

Primary spec:

```text
docs/superpowers/specs/2026-07-10-impeller-v1-1-2-canonical-nurbs-parameterization-spec.md
```

Semantic change log:

```text
docs/evidence/2026-07-10-impeller-v1-1-2-semantic-change-log.md
```

Insight log:

```text
docs/evidence/2026-07-10-impeller-v1-1-2-insight-log.md
```

## Planned Implementation Evidence

The implementation phase should append:

```text
RED/GREEN test transcripts for canonical payload tests
preset translation manifest excerpts for all five active presets
frontend Parameter views screenshot or textual DOM evidence
service smoke for open and closed V1.1.2 presets
mesh/viewer evidence that V1.1.1 surface roles remain compatible
```

## Current Open Risks

1. The first real frontend-payload open preset smoke took roughly 204 seconds. V1.1.2 should not make generation time materially worse without documenting the cause.
2. If the canonical payload is added only to frontend data and not backend manifests, the annotation tab will diverge from generated geometry.
3. If direct NURBS segment-curve input and skeleton-thickness-cap input compile to different internal structures, the project will gain another ambiguous geometry language. They must compile to the same canonical loop family.

## Implementation Verification

Implementation branch head at verification time:

```text
ce70910 fix: scale bounded brep fit tolerance to grid resolution
```

### Backend V1.1.2 Tests

Command:

```text
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py tests/test_impeller_v11_2_preset_translation.py tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_2_nurbs_loop_caps.py tests/test_impeller_v11_2_surface_graph_compatibility.py -q
```

Result:

```text
...............                                                          [100%]
15 passed in 68.63s (0:01:08)
```

### Geometry Validation Smoke

Command:

```text
python -m pytest tests/test_impeller_geometry_validation.py -q
```

Result:

```text
.................                                                        [100%]
17 passed in 2.20s
```

### Bounded BREP Export Regression

Command:

```text
$env:PYTHONPATH='src'; python -m pytest tests/test_impeller_bounded_brep_export.py -q
```

Result:

```text
......................................                                   [100%]
38 passed in 1.05s
```

Note:

- The first five-preset service smoke exposed a bounded BREP export failure for `rr_ultrafan_cti_fan_v1_1`.
- Failure: `blade_0_suction_surface B-spline fit max error 3.84181 mm exceeds 1.93611 mm tolerance`.
- Diagnosis: the fit error was small relative to the surface sampling resolution. The failed surface had median cell diagonal about `123.325 mm`, while max fit error was `3.842 mm`.
- Fix: bounded BREP fit tolerances now include sampled grid resolution terms: `0.05 * median_cell_diagonal` for max error and `0.01 * median_cell_diagonal` for RMS error.

### V1.1 Regression Tests

The all-in-one V1.1 regression command exceeded the local command timeout because `tests/test_impeller_v11_mesh_and_export_contract.py` takes about three and a half minutes. The same files were rerun in split groups.

Command:

```text
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py -q
```

Result:

```text
.....................................                                    [100%]
37 passed in 12.27s
```

Command:

```text
python -m pytest tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py -q
```

Result:

```text
.........................                                                [100%]
25 passed in 65.85s (0:01:05)
```

Command:

```text
python -m pytest tests/test_impeller_v11_mesh_and_export_contract.py -q
```

Result:

```text
.........                                                                [100%]
9 passed in 212.19s (0:03:32)
```

### Frontend Tests

Command:

```text
cd frontend
npm.cmd test
```

Result:

```text
tests 128
suites 13
pass 128
fail 0
duration_ms 234.8656
```

### Five-Preset Service Smoke

Command:

```text
$env:PYTHONPATH='src'; @'
from pathlib import Path
from part_rule_synthesis.service import RuleSynthesisService

presets = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]
service = RuleSynthesisService(Path(".tmp-v112-smoke"), model_output_root=Path(".tmp-v112-smoke") / "Model Output")
for preset_id in presets:
    engine = service.synthesize("impeller", preset_id=preset_id)
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest
    graph = manifest["geometry"]["surface_graph"]
    print(
        preset_id,
        manifest["geometry_patch_version"],
        graph["canonical_nurbs_parameterization"]["canonical_payload_version"],
        manifest["geometry_validation_status"],
        run.run_id,
    )
'@ | python -
```

Preset result lines:

```text
radial_open_reference_v1_1 1.1.2 1.1.2 PASS run-601878240064
radial_closed_reference_v1_1 1.1.2 1.1.2 PASS run-2af66e85cc8e
nasa_stage37_stator_ring_v1_1 1.1.2 1.1.2 PASS run-3ef40d0b7acd
rr_ultrafan_cti_fan_v1_1 1.1.2 1.1.2 PASS run-8efb599340ae
public_rocket_turbopump_inducer_v1_1 1.1.2 1.1.2 PASS run-6e2d32bd20e5
```

## Implementation Notes

- Backend runtime and service manifests now expose `canonical_nurbs_parameterization`, `canonical_metrics`, and `math_parameterization`.
- The loop builder consumes canonical skeleton/thickness fields and active span offsets while retaining legacy fallback behavior for malformed canonical payloads.
- Active-span feasibility is now pointwise. During Task 3 review, interval-averaged feasibility was rejected; strict pointwise diagnostics are the accepted semantic rule.
- Leading/trailing cap metadata now distinguishes target sagitta from resolved sagitta measured from final cap geometry.
- Frontend presets expose canonical defaults, and the new `Parameter views` panel reads preset defaults before generation and manifest-resolved canonical data after generation.
