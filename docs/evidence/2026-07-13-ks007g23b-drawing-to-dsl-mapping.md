# KS007G23B Drawing-To-DSL Mapping

Date: 2026-07-13

## Scope

This record maps the customer-supplied A3 drawing `KS007G23B.pdf` into the
V1.1 blade-to-blade review DSL. The source SHA-256 is
`a5dd9e79dbbb67f1bcfd74b51baa8a6c95661bd75a1eb1e111446bdd80c29282`.

The drawing explicitly states that unspecified dimensions are defined by a 3D
model. That model was not supplied. Consequently this preset is `review-grade`
and is not a manufacturing reconstruction.

## Direct Drawing Facts

| Drawing fact | Value | Confidence |
| --- | ---: | ---: |
| Drawing number | KS007G23B | 1.00 |
| Part name | Turbine impeller | 1.00 |
| Material | GH4169 | 1.00 |
| Blade population | 13 equally spaced blades | 1.00 |
| Maximum diameter | 103.2 mm | 1.00 |
| Overall axial length | 36.5 mm | 1.00 |
| Stepped bore diameter used by this reduced preset | 15.8 mm | 0.90 |
| Front hub diameter used as inner blade-domain diameter | 25 mm | 0.80 |
| Nominal mass | 516.7 g | 1.00 |
| Operating speed | 125000 rpm | 1.00 |
| Maximum working temperature | 800 C | 1.00 |

## DSL Construction Parameters

| DSL parameter | Seed | Confidence | Basis |
| --- | ---: | ---: | --- |
| `blade_count` | 13 | 1.00 | Direct note |
| `inlet_radius_mm` | 12.5 | 0.80 | Ø25 interpreted as inner blade-domain diameter |
| `exit_radius_mm` | 51.6 | 1.00 | Ø103.2 / 2 |
| `inlet_blade_height_mm` | 6.5 | 0.35 | Section-view profile estimate |
| `outlet_blade_height_mm` | 5.75 | 0.65 | Direct dimension interpreted as local outer height |
| `inlet_blade_angle_deg` | 72 | 0.30 | View estimate |
| `outlet_blade_angle_deg` | 28 | 0.30 | View estimate |
| `blade_thickness_mm` | 1.2 | 0.25 | Engineering seed; not dimensioned |
| `hub_curve_height_mm` | 36.5 | 0.85 | Overall length interpreted as meridional height |
| `mounting_bore_radius_mm` | 7.9 | 0.90 | Ø15.8 / 2; reduced from stepped/splined bore |
| `blade_wrap_deg` | 82 | 0.35 | 1:1 top-view estimate |
| `blade_lean_deg` | 8 | 0.25 | Engineering seed |
| `leading_edge_lean_deg` | 5 | 0.25 | Engineering seed |
| `trailing_edge_lean_deg` | -6 | 0.25 | Engineering seed |
| `leading_edge_sweep_mm` | 1.5 | 0.25 | Engineering seed |
| `trailing_edge_sweep_mm` | -1.0 | 0.25 | Engineering seed |
| `root_fillet_radius_mm` | 0.8 | 0.20 | Undimensioned visible blend |
| `leading_edge_radius_mm` | 0.3 | 0.20 | Undimensioned |
| `trailing_edge_radius_mm` | 0.2 | 0.20 | Undimensioned |
| `tip_edge_radius_mm` | 0.25 | 0.20 | Undimensioned |
| `hub_wall_thickness_mm` | 2.5 | 0.70 | End-wall dimension interpreted by DSL |
| `hub_bottom_thickness_mm` | 5.75 | 0.75 | End dimension interpreted by DSL |
| `hub_top_cap_thickness_mm` | 0.8 | 0.75 | Direct end-face dimension interpreted by DSL |
| `hub_chamfer_radius_mm` | 0.3 | 0.20 | Edge-break seed; radius unspecified |

## Loop And Support Parameters

| Parameter group | Seed | Confidence | Basis |
| --- | --- | ---: | --- |
| Main/splitter count | 13 / 0 | 1.00 | Direct drawing population |
| Main active interval | 0.05 to 0.96 | 0.45 | Top-view blade envelope |
| Maximum/average thickness | 1.4 / 1.0 mm | 0.25 | Missing 3D model |
| Root width/lift | 0.8 / 1.0 mm | 0.25 | Missing root dimensions |
| Main flow turn | 34 mm in S-Q | 0.35 | Derived from estimated wrap |
| Spanwise turn / bow | 5.0 / 1.5 mm | 0.25 | Missing 3D model |
| LE/TE cap roundness | 0.56 / 0.52 | 0.20 | Review seed |
| Tip mode | open tip dome | 0.98 | Open wheel is explicit in views |
| Hub profile | six R-Z controls | 0.55 | Section fit constrained by direct envelopes |
| Tip profile | six R-Z controls | 0.50 | Visible envelope fit |
| Control/sample counts | dense V1.1 review policy | 1.00 | Software resolution policy, not physical inference |

## Unrepresented Drawing Features

- DIN5480 14-tooth internal involute spline and its tolerance table.
- The stepped bore authority beyond the reduced Ø15.8 cylindrical bore.
- Three equally spaced M5 holes and their positional tolerance.
- Balancing-removal faces, marking, surface finish, heat treatment, GD&T, and
  manufacturing tolerances.
- Exact blade freeform surfaces and thickness distribution from the referenced
  3D model.

These omissions must remain visible in UI/export maturity labels. The preset
must not be described as certified CAD or as a production-equivalent part.
