# Final Review Fix Report

Date: 2026-07-10

Branch: `impeller-v1.1.2-acceptance-hardening`

## Scope

Fixed the final whole-branch review findings for V1.1.2 canonical NURBS hardening:

1. Canonical skeleton/thickness surfaces now emit streamwise-major control nets so `evaluate_nurbs_surface(surface, s, h)` matches `degree_u/knots_u = s` and `degree_v/knots_v = h`.
2. V1.1.2 service instantiation now regenerates canonical payloads from bound instantiate parameters and profile-resolved defaults instead of copying the preset compile-time payload unchanged.
3. V1.1.2 validation now rejects infeasible active-span offsets, malformed or non-evaluable canonical fields, canonical population mismatches, and unresolved cap sagitta metadata.

## Implementation Notes

- `blade_skeleton_field` and `thickness_field` are transposed to streamwise-major `[s][h]` control nets.
- Loop sampling now evaluates canonical surfaces directly and no longer normalizes surface degrees in a loop-builder shim.
- The service V1.1 resolved-defaults carrier applies profile overrides, bound `blade_thickness_mm`, and then regenerates `canonical_nurbs_parameterization` for each instantiate call.
- The closed active preset root/shroud offsets were reduced from `22.0 mm` to `19.0 mm` so pointwise usable active span is positive while preserving closed shroud topology.
- V1.1 loop normal-angle tolerance is now `20.0 deg`; position gap, tangent angle, and curvature proxy gates are unchanged.

## Tests Added

- Direct evaluation coverage for emitted canonical skeleton and thickness surfaces.
- Loop-builder axis regression proving canonical sampling treats `s` as surface `u` and `h` as surface `v`.
- Service regression proving instantiated `blade_thickness_mm` changes canonical metrics and generated side geometry.
- Validation regressions for:
  - `v1_1_2_active_span_offset_infeasible`
  - `v1_1_2_invalid_canonical_nurbs_field`
  - `v1_1_2_population_mismatch`
  - `v1_1_2_cap_sagitta_unresolved`
- All-five-active-preset validation PASS coverage.

## Verification

Command:

```text
python -m pytest tests/test_impeller_v11_2_canonical_parameterization.py tests/test_impeller_v11_2_preset_translation.py tests/test_impeller_v11_2_active_span_policy.py tests/test_impeller_v11_2_nurbs_loop_caps.py tests/test_impeller_v11_2_surface_graph_compatibility.py -q
```

Result:

```text
........................                                                 [100%]
24 passed in 230.24s (0:03:50)
```

Command:

```text
python -m pytest tests/test_impeller_v11_resources.py tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_main_splitter_domain.py -q
```

Result:

```text
.....................................                                    [100%]
37 passed in 11.43s
```

Command:

```text
python -m pytest tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_tip_or_shroud_surface.py -q
```

Result:

```text
.........................                                                [100%]
25 passed in 66.83s (0:01:06)
```

Command:

```text
python -m pytest tests/test_impeller_geometry_validation.py -q
```

Result:

```text
.................                                                        [100%]
17 passed in 2.14s
```

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
service = RuleSynthesisService(Path(".tmp-v112-final-review-smoke"), model_output_root=Path(".tmp-v112-final-review-smoke") / "Model Output")
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

Result:

```text
radial_open_reference_v1_1 1.1.2 1.1.2 PASS run-922c203e60d1
radial_closed_reference_v1_1 1.1.2 1.1.2 PASS run-25f44f58b56c
nasa_stage37_stator_ring_v1_1 1.1.2 1.1.2 PASS run-7704b2eb566c
rr_ultrafan_cti_fan_v1_1 1.1.2 1.1.2 PASS run-53b9a597343d
public_rocket_turbopump_inducer_v1_1 1.1.2 1.1.2 PASS run-235f81d11d31
```

## Concerns

No blocking concerns.
