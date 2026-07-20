# Impeller V1.1.6 R16.23 Hub Support Union Verification

Date: 2026-07-19

## Scope

- Runtime: V1.1.6 STEP reconstruction review path.
- Change: complementary STEP hub-face semantic union and full periodic
  circumferential coverage gate.
- Non-goals: blade reconstruction mathematics, unsupported spline/holes,
  bottom boss, and exact certified B-Rep sewing.

## Synthetic Contract Tests

Commands:

```powershell
python -m pytest tests/test_impeller_v11_6_axis_first_pipeline.py -k "profile_conformant_split_hub_face or split_hub_source_union or hub_coverage_gate_is_independent or shared_hub_support_requires or promoted_hub_face or hub_source_union_rejects_uniformly or initial_hub_coverage or root_attachment_cannot or multiple_support_owners or exact_hub_boundary_sampling or periodic_representative_excludes or pattern_population_authority" -q
python -m pytest tests/test_impeller_v11_6_axis_first_pipeline.py -q
python -m pytest tests/test_impeller_v11_6_axis_first_contract.py -q
python -m pytest tests/test_impeller_v11_6_step_audit.py -q
python -m pytest tests/test_impeller_v11_6_comparison_scope.py -q
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m pytest tests/test_impeller_v11_6_pattern_reconstruction.py -q
python -m pytest tests/test_impeller_v11_6_section_curve_surfaces.py -q
```

Results:

- Hub union and independent-review counterexamples: `14 passed`.
- Axis-first contract: `58 passed`.
- STEP audit: `54 passed, 1 skipped`.
- Supported comparison scope: `13 passed`.
- Complete axis-first pipeline file: `67 passed in 201.82s`.
- Pattern reconstruction: `28 passed`.
- Direct section surfaces: `27 passed`.
- Full listed non-overlapping regression set: `247 passed, 1 skipped`.

The split-face fixture deliberately assigns the complementary candidate to the
wrong coarse periodic instance. The accepted owner must come from the adjacent
authenticated hub patch. A root-transition candidate remains protected even
when it is profile-conformant. Multiple adjacent support owners, any unreadable
exact boundary edge, uniformly small absolute pitch coverage, and absence of a
valid complement all fail closed with the stable coverage reason.
The prefilter also rejects a zero-angle initial coverage reference through the
same stable reason instead of leaking a division error.
Main and splitter gates are evaluated independently. A shared support patch is
not exempt: its exact trimmed-boundary union must pass an absolute full-circle
gate. Empty or one-point edge samples are invalid exact-boundary evidence.

## Real STEP Evidence

Source:

- Audit source: `step-audit-7aedfbda8d2348f9/source.step`
- SHA-256:
  `1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5`
- API path: `load_step_source` -> `resolve_canonical_frame` ->
  `classify_impeller_semantics` -> `_source_inventory` ->
  `_recover_support_evidence`.
- Latest support plus periodic-recovery elapsed time: `72.358 s` (local warm
  run; recorded as reproducibility context, not a performance acceptance).

Observed R16.23 contract:

- Contract id: `impeller_v1_1_6_hub_support_source_union_r16_23`.
- Initial hub faces: 13.
- Promoted complements: `source_face_00056`, `source_face_00134`.
- Final hub semantic union: 15 source faces.
- Periodic coverage: 13/13 instances complete.
- Population gate: `main`, 13 instances.
- Expected pitch angle: `27.692307692 deg`.
- Minimum absolute coverage per pitch: `22.153846154 deg`.
- Coverage mode:
  `every_periodic_pitch_absolute_and_population_relative_angular_support`.
- `full_revolution_covered`: `true`.
- `source_face_00056` role: `hub_flowpath_support`.
- `source_face_00056` periodic owner after final partition: `null`.
- Periodic recovery retains `source_face_00056` in the coarse provenance ledger
  but excludes it from final periodic `source_ids`; neither promoted face is in
  the blade construction domain.
- Promoted-face overlap with final pattern authority: empty.
- Hub profile RMS: `0.012253156 mm`.
- Hub profile P95: `0.020685434 mm`.
- Hub profile maximum: `0.022007953 mm`.

The low final residual and rejection of nearby root candidates show that the
union restores omitted hub material without widening the hub profile into the
blade-root transition domain.

## Maturity Boundary

This is review-grade semantic and sampled-geometry evidence. For periodic
passage patches, every pitch must pass both a population-specific
`0.8 * (360 / population_count)` absolute angular floor and a `0.8` fraction
of that population's median bare-hub angular support. Shared support faces use
an absolute `0.8 * 360` boundary-union gate. These gates tolerate bounded blade
attachment cutouts without allowing uniformly incomplete sectors to normalize
themselves into a false pass. They are not a claim that every azimuth has an
untrimmed hub point at every meridional station.
