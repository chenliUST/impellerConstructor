# Impeller V1.1.4 Verification Evidence

## Measured Geometry

Open preset:

```text
splitter passage fraction min  0.499932847
splitter passage fraction max  0.500102986
support angle min              70.118963685 deg
support angle max             110.110288953 deg
minimum active blade height   102.693144614 mm
required active blade height   60.0 mm
```

Closed preset:

```text
support angle min              78.761655496 deg
support angle max             104.649048670 deg
minimum active blade height    61.957134107 mm
required active blade height   55.0 mm
shroud attachment width min    12.6161 mm
```

## Automated Verification

```text
python -m pytest tests/test_impeller_v11_4_release.py tests/test_impeller_v11_main_splitter_domain.py -q
16 passed

python -m pytest tests/test_impeller_v11_3_service_manifest.py::test_all_active_presets_expose_service_inspection_contracts -q
1 passed; all five presets synthesized, validated and exported

python -m pytest tests/test_impeller_v11_3_parameter_inspection_contract.py -q
11 passed

python -m pytest tests/test_impeller_v11_blade_to_blade_loop_domain.py tests/test_impeller_v11_loop_c2_continuity.py tests/test_impeller_v11_root_attachment_surface.py tests/test_impeller_v11_six_face_surface_family.py tests/test_impeller_v11_tip_or_shroud_surface.py -q
43 passed

python -m pytest tests/test_impeller_v11_2_surface_graph_compatibility.py -q -k "not service"
6 passed, 2 service tests deselected; equivalent current open/closed service export smokes passed separately

cd frontend
npm.cmd test
205 passed

npm.cmd run build
frontend build check passed
```

## Local Runtime

```text
backend  http://127.0.0.1:8061
frontend http://127.0.0.1:5199
```

HTTP open-preset smoke returned runtime `1.1.4`, inspection contract `1.1.4`,
geometry validation `PASS`, splitter positioning `PASS`, and support-profile
contract `PASS`.

The 1600 x 1000 empty-state visual smoke confirmed a full-width CAD canvas, the
absence of a left sidebar, and exactly two active workspaces: CAD Review and
Engineering Drawing.

## Semantic Drawing And Preset Payload Verification

```text
python -m pytest tests/test_impeller_v11_4_engineering_drawing.py -q
5 passed; all five preset-only HTTP payloads accepted, including four zero-splitter presets

python -m pytest tests/test_impeller_v11_4_release.py tests/test_impeller_v11_blade_to_blade_loop_domain.py -q
12 passed

cd frontend
npm.cmd test
211 passed

npm.cmd run build
frontend build check passed
```

Browser verification against backend `8061` and frontend `5199` confirmed:

- Open Top drawing: one complete orthographic outline, three named active-span
  sections, 16 rendered dimensions/notes, and no UV-grid traversal.
- Open Meridional drawing: 12 NURBS control points, two dashed control polygons,
  seven deduplicated engineering dimensions, and separate actual support curves.
- Open S-Q drawing: two section rows and one shared high-DPI WebGL canvas at
  1054 x 720 device pixels; both representative blades were nonblank.
- Closed preset generated without a population error and emitted one main-blade
  S-Q row with no synthetic splitter row.
- Browser console contained no application warnings or errors during the drawing
  view transitions.
