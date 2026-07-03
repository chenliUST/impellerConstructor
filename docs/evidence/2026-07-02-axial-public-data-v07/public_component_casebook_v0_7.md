# Impeller Constructor V0.7 public and analogy casebook

Updated: 2026-07-02

This casebook records the V0.7 constructor inputs and generated model snapshots. The aviation and turbopump cases use public dimensions where available; missing CAD-grade twist, sweep, thickness, hub, bore, and fillet values are marked as visual proxy values. The gear, turbine, and worm examples are mechanical analogy cases that exercise the same mathematical construction rules; they are not standards-compliant gear or turbine design solvers.

The new snapshot workflow stores each generated model as `manifest + OBJ + STL + STEP + PNG snapshot` under `model_snapshots/<case-id>/`. These PNGs are rendered offline from OBJ exports, so they are not affected by frontend scroll position or viewport cropping.

## References

- NASA Rotor 67 public report: `https://ntrs.nasa.gov/api/citations/20050196726/downloads/20050196726.pdf`
- NASA Rotor 37 / Stage 37 public geometry summary: `https://lava-wiki.meca.polymtl.ca/_media/public/modeles/rotor_37/rotor37.pdf`
- NASA Rotor 37 blade count and hub-tip ratio summary: `https://www.jstage.jst.go.jp/article/jgpp/2/1/2_24/_pdf`
- NASA stator 37 vane count reference: `https://ntrs.nasa.gov/api/citations/20030038949/downloads/20030038949.pdf`
- NASA Source Diagnostic Test R4 fan: `https://ntrs.nasa.gov/api/citations/20050175875/downloads/20050175875.pdf`
- NASA Source Diagnostic Fan II 22-inch parameters: `https://ntrs.nasa.gov/citations/20220009115`
- RR UltraFan official page: `https://www.rolls-royce.com/innovation/ultrafan.aspx`
- RR UltraFan 80 demonstrator fact sheet: `https://www.rolls-royce.com/~/media/Files/R/Rolls-Royce/documents/others/ultrafan-80-demonstrator-fact%20sheet.pdf`
- RR composite fan blade press release: `https://www.rolls-royce.com/media/press-releases/2020/11-02-2020-intelligentengine-rr-starts-manufacture-of-world-largest-fan-blades.aspx`
- Public 18-blade UltraFan fan-set report: `https://www.compositesworld.com/news/rolls-royce-starts-manufacture-of-worlds-largest-fan-blades-made-with-composites-for-ultrafan-demonstrator`
- NASA SP-8052 liquid rocket engine turbopump inducers: `https://ntrs.nasa.gov/citations/19710025474`
- NASA SR-7L / Large Scale Advanced Prop-Fan static rotor report: `https://ntrs.nasa.gov/api/citations/19900003301/downloads/19900003301.pdf`
- KHK basic gear terminology and calculation: `https://khkgears.net/new/gear_knowledge/abcs_of_gears-b/basic_gear_terminology_calculation.html`
- KHK gear dimension calculations: `https://khkgears.net/new/gear_knowledge/gear_technical_reference/calculation_gear_dimensions.html`
- SDP/SI worm gear mesh geometry: `https://sdp-si.com/resources/elements-of-metric-gear-technology/page5.php`
- NASA variable-speed power turbine research: `https://ntrs.nasa.gov/api/citations/20120013209/downloads/20120013209.pdf`
- NASA turbo-design repository: `https://github.com/nasa/turbo-design`

## Summary

| Case ID | Tags | Public/proxy anchor | Run | Snapshot | Exact input/export directory |
| --- | --- | --- | --- | --- | --- |
| `public-nasa-rotor67-axial-blisk` | public-data, axial, blisk, rotor, v0.7 | NASA Rotor 67: 22 blades, published annulus dimensions and hub-tip ratios. | `PASS`, `run-0f9907d9c350` | `model_snapshots/public-nasa-rotor67-axial-blisk/public-nasa-rotor67-axial-blisk.snapshot.png` | `model_snapshots/public-nasa-rotor67-axial-blisk/` |
| `public-nasa-rotor37-compressor-blisk` | public-data, axial, blisk, compressor, v0.7 | NASA Rotor 37: 36 blades, public hub-tip ratio / annulus scale. | `PASS`, `run-cb00a9057ba2` | `model_snapshots/public-nasa-rotor37-compressor-blisk/public-nasa-rotor37-compressor-blisk.snapshot.png` | `model_snapshots/public-nasa-rotor37-compressor-blisk/` |
| `public-nasa-stage37-stator-ring` | public-data, axial, stator, ring, v0.7 | NASA Stage/Stator 37: 46 stator vanes, Rotor/Stage 37 annulus scale. | `PASS`, `run-839704c71e95` | `model_snapshots/public-nasa-stage37-stator-ring/public-nasa-stage37-stator-ring.snapshot.png` | `model_snapshots/public-nasa-stage37-stator-ring/` |
| `public-nasa-sdt-r4-turbofan-fan` | public-data, axial, fan, turbofan, v0.7 | NASA SDT R4 fan: 22-inch class fan, 22 rotor blades, low hub ratio. | `PASS`, `run-ffa59c9fd3cd` | `model_snapshots/public-nasa-sdt-r4-turbofan-fan/public-nasa-sdt-r4-turbofan-fan.snapshot.png` | `model_snapshots/public-nasa-sdt-r4-turbofan-fan/` |
| `public-rr-ultrafan-cti-fan` | public-data, axial, fan, ultrafan, v0.7 | RR UltraFan: 140-inch fan system, CTi fan blades, public 18-blade fan-set report; hub shape is a visual proxy. | `PASS`, `run-caf0f3b01b09` | `model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.snapshot.png` | `model_snapshots/public-rr-ultrafan-cti-fan/` |
| `public-rr-ultrafan-ogv-ring` | public-data, axial, stator, ultrafan, v0.7 | RR UltraFan scale OGV ring: 140-inch fan annulus anchor; OGV count/airfoil are proxy values. | `PASS`, `run-0b28bbde026d` | `model_snapshots/public-rr-ultrafan-ogv-ring/public-rr-ultrafan-ogv-ring.snapshot.png` | `model_snapshots/public-rr-ultrafan-ogv-ring/` |
| `public-liquid-rocket-turbopump-inducer` | public-data, axial, inducer, pump, v0.7 | NASA SP-8052 inducer reference; 3-blade screw inducer dimensions are visual proxy values. | `PASS`, `run-913ddefa68d5` | `model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.snapshot.png` | `model_snapshots/public-liquid-rocket-turbopump-inducer/` |
| `public-nasa-sr7l-propfan` | public-data, axial, propeller, propfan, v0.7 | NASA SR-7L: 2.74 m / 9 ft diameter, 8 blades, swept thin blades. | `PASS`, `run-ac63c0a284bc` | `model_snapshots/public-nasa-sr7l-propfan/public-nasa-sr7l-propfan.snapshot.png` | `model_snapshots/public-nasa-sr7l-propfan/` |
| `reference-spur-gear-tooth-ring` | mechanical-analogy, gear, radial, v0.7 | KHK/RoyMech gear module relations used as scale reference; V0.7 blades proxy straight teeth. | `PASS`, `run-c54c8ed5b0c8` | `model_snapshots/reference-spur-gear-tooth-ring/reference-spur-gear-tooth-ring.snapshot.png` | `model_snapshots/reference-spur-gear-tooth-ring/` |
| `reference-axial-turbine-rotor` | mechanical-analogy, turbine, axial, rotor, v0.7 | NASA turbine/turbomachinery references used as topology reference; dimensions are proxy values. | `PASS`, `run-2e89991e13ce` | `model_snapshots/reference-axial-turbine-rotor/reference-axial-turbine-rotor.snapshot.png` | `model_snapshots/reference-axial-turbine-rotor/` |
| `reference-double-start-worm` | mechanical-analogy, worm, screw, v0.7 | KHK/SDP-SI worm gear geometry references used as topology reference; dimensions are proxy values. | `PASS`, `run-740be69b4400` | `model_snapshots/reference-double-start-worm/reference-double-start-worm.snapshot.png` | `model_snapshots/reference-double-start-worm/` |

## Updated Hub Shape Snapshots

### `public-rr-ultrafan-cti-fan`

Updated in this pass: hub_profile is no longer near-cylindrical; it uses a nose-ogive control polygon from small nose radius to large aft hub radius. Extra hub-only and R-Z profile snapshots are included.

- Full model snapshot: `model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.snapshot.png`
- Hub-only OBJ snapshot: `model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.hub.snapshot.png`
- R-Z profile controls: `model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.hub-profile.png`

### `public-liquid-rocket-turbopump-inducer`

Updated in this pass: hub_profile is a bullet/nose-ogive shaft instead of a cylinder. Extra hub-only and R-Z profile snapshots are included.

- Full model snapshot: `model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.snapshot.png`
- Hub-only OBJ snapshot: `model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.hub.snapshot.png`
- R-Z profile controls: `model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.hub-profile.png`

## Construction Data

### `public-nasa-rotor67-axial-blisk`

- Name: Public NASA Rotor 67 axial blisk
- Run: `run-0f9907d9c350` / `PASS`
- Surfaces: `141`
- Full model snapshot: `model_snapshots/public-nasa-rotor67-axial-blisk/public-nasa-rotor67-axial-blisk.snapshot.png`
- Exact generation JSON: `model_snapshots/public-nasa-rotor67-axial-blisk/public-nasa-rotor67-axial-blisk.generation.json`
- Exports: `{"manifest": "model_snapshots/public-nasa-rotor67-axial-blisk/public-nasa-rotor67-axial-blisk.manifest.json", "obj": "model_snapshots/public-nasa-rotor67-axial-blisk/public-nasa-rotor67-axial-blisk.obj", "step": "model_snapshots/public-nasa-rotor67-axial-blisk/public-nasa-rotor67-axial-blisk.step", "stl": "model_snapshots/public-nasa-rotor67-axial-blisk/public-nasa-rotor67-axial-blisk.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "fan_or_blower",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 22,
    "inlet_radius_mm": 95.9,
    "exit_radius_mm": 255.7,
    "inlet_blade_height_mm": 159.8,
    "outlet_blade_height_mm": 126.6,
    "hub_curve_height_mm": 92,
    "mounting_bore_radius_mm": 36,
    "blade_wrap_deg": 74,
    "blade_lean_deg": 18,
    "leading_edge_lean_deg": 8,
    "trailing_edge_lean_deg": -10,
    "leading_edge_sweep_mm": 8,
    "trailing_edge_sweep_mm": -10,
    "blade_thickness_mm": 4.8,
    "root_fillet_radius_mm": 1.8,
    "leading_edge_radius_mm": 0.8,
    "trailing_edge_radius_mm": 0.45,
    "tip_edge_radius_mm": 0.45,
    "hub_wall_thickness_mm": 7,
    "hub_bottom_thickness_mm": 10,
    "hub_top_cap_thickness_mm": 4,
    "hub_chamfer_radius_mm": 1,
    "hood_wall_thickness_mm": 4,
    "hood_chamfer_radius_mm": 1
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          95.9,
          92
        ],
        [
          99,
          72
        ],
        [
          105,
          48
        ],
        [
          110,
          25
        ],
        [
          114,
          10
        ],
        [
          115.9,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          255.7,
          93
        ],
        [
          253.2,
          73
        ],
        [
          249.8,
          49
        ],
        [
          246.4,
          26
        ],
        [
          244.1,
          11
        ],
        [
          242.5,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.2,
            -7
          ],
          [
            0.55,
            -38
          ],
          [
            0.82,
            -61
          ],
          [
            1,
            -74
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            8
          ],
          [
            0.35,
            24
          ],
          [
            0.7,
            12
          ],
          [
            1,
            -10
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            -0.05
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0.07
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0.06
          ],
          [
            0.5,
            0
          ],
          [
            1,
            -0.08
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            4.8
          ],
          [
            0.45,
            3.9
          ],
          [
            1,
            2.4
          ]
        ]
      }
    }
  }
}
```

### `public-nasa-rotor37-compressor-blisk`

- Name: Public NASA Rotor 37 compressor blisk
- Run: `run-cb00a9057ba2` / `PASS`
- Surfaces: `225`
- Full model snapshot: `model_snapshots/public-nasa-rotor37-compressor-blisk/public-nasa-rotor37-compressor-blisk.snapshot.png`
- Exact generation JSON: `model_snapshots/public-nasa-rotor37-compressor-blisk/public-nasa-rotor37-compressor-blisk.generation.json`
- Exports: `{"manifest": "model_snapshots/public-nasa-rotor37-compressor-blisk/public-nasa-rotor37-compressor-blisk.manifest.json", "obj": "model_snapshots/public-nasa-rotor37-compressor-blisk/public-nasa-rotor37-compressor-blisk.obj", "step": "model_snapshots/public-nasa-rotor37-compressor-blisk/public-nasa-rotor37-compressor-blisk.step", "stl": "model_snapshots/public-nasa-rotor37-compressor-blisk/public-nasa-rotor37-compressor-blisk.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "compressor",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 36,
    "inlet_radius_mm": 176.4,
    "exit_radius_mm": 253.7,
    "inlet_blade_height_mm": 77.3,
    "outlet_blade_height_mm": 75.6,
    "hub_curve_height_mm": 64,
    "mounting_bore_radius_mm": 70,
    "blade_wrap_deg": 56,
    "blade_lean_deg": 10,
    "leading_edge_lean_deg": 5,
    "trailing_edge_lean_deg": -8,
    "leading_edge_sweep_mm": 4,
    "trailing_edge_sweep_mm": -6,
    "blade_thickness_mm": 2.8,
    "root_fillet_radius_mm": 1.1,
    "leading_edge_radius_mm": 0.45,
    "trailing_edge_radius_mm": 0.3,
    "tip_edge_radius_mm": 0.3,
    "hub_wall_thickness_mm": 5,
    "hub_bottom_thickness_mm": 7,
    "hub_top_cap_thickness_mm": 3,
    "hub_chamfer_radius_mm": 1,
    "hood_wall_thickness_mm": 3,
    "hood_chamfer_radius_mm": 1
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          176.4,
          64
        ],
        [
          176.8,
          51
        ],
        [
          177.4,
          38
        ],
        [
          178,
          24
        ],
        [
          178.5,
          12
        ],
        [
          179,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          253.7,
          65
        ],
        [
          253.4,
          52
        ],
        [
          253,
          39
        ],
        [
          252.6,
          25
        ],
        [
          252.3,
          13
        ],
        [
          252,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.2,
            -6
          ],
          [
            0.55,
            -29
          ],
          [
            0.82,
            -48
          ],
          [
            1,
            -56
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            5
          ],
          [
            0.45,
            16
          ],
          [
            1,
            -8
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            -0.035
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0.055
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0.045
          ],
          [
            0.5,
            0
          ],
          [
            1,
            -0.06
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            2.8
          ],
          [
            0.5,
            2.2
          ],
          [
            1,
            1.4
          ]
        ]
      }
    }
  }
}
```

### `public-nasa-stage37-stator-ring`

- Name: Public NASA Stage 37 stator ring
- Run: `run-839704c71e95` / `PASS`
- Surfaces: `290`
- Full model snapshot: `model_snapshots/public-nasa-stage37-stator-ring/public-nasa-stage37-stator-ring.snapshot.png`
- Exact generation JSON: `model_snapshots/public-nasa-stage37-stator-ring/public-nasa-stage37-stator-ring.generation.json`
- Exports: `{"manifest": "model_snapshots/public-nasa-stage37-stator-ring/public-nasa-stage37-stator-ring.manifest.json", "obj": "model_snapshots/public-nasa-stage37-stator-ring/public-nasa-stage37-stator-ring.obj", "step": "model_snapshots/public-nasa-stage37-stator-ring/public-nasa-stage37-stator-ring.step", "stl": "model_snapshots/public-nasa-stage37-stator-ring/public-nasa-stage37-stator-ring.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "closed",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "compressor",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 46,
    "inlet_radius_mm": 176.4,
    "exit_radius_mm": 253.7,
    "inlet_blade_height_mm": 77.3,
    "outlet_blade_height_mm": 75.6,
    "hub_curve_height_mm": 60,
    "mounting_bore_radius_mm": 82,
    "blade_wrap_deg": 24,
    "blade_lean_deg": 2,
    "leading_edge_lean_deg": -4,
    "trailing_edge_lean_deg": 5,
    "leading_edge_sweep_mm": 2,
    "trailing_edge_sweep_mm": -3,
    "blade_thickness_mm": 2.3,
    "root_fillet_radius_mm": 0.9,
    "leading_edge_radius_mm": 0.35,
    "trailing_edge_radius_mm": 0.25,
    "tip_edge_radius_mm": 0.25,
    "hub_wall_thickness_mm": 4.5,
    "hub_bottom_thickness_mm": 6,
    "hub_top_cap_thickness_mm": 3,
    "hub_chamfer_radius_mm": 0.8,
    "hood_wall_thickness_mm": 3,
    "hood_chamfer_radius_mm": 0.8
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          176.4,
          60
        ],
        [
          176.8,
          48
        ],
        [
          177.3,
          36
        ],
        [
          177.8,
          23
        ],
        [
          178.2,
          11
        ],
        [
          178.6,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          253.7,
          61
        ],
        [
          253.4,
          49
        ],
        [
          253,
          37
        ],
        [
          252.6,
          24
        ],
        [
          252.3,
          12
        ],
        [
          252,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.25,
            4
          ],
          [
            0.6,
            15
          ],
          [
            1,
            24
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            -6
          ],
          [
            0.5,
            2
          ],
          [
            1,
            5
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            -0.02
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0.03
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0.04
          ],
          [
            0.5,
            0
          ],
          [
            1,
            -0.04
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            2.3
          ],
          [
            0.4,
            2
          ],
          [
            1,
            1.2
          ]
        ]
      }
    }
  }
}
```

### `public-nasa-sdt-r4-turbofan-fan`

- Name: Public NASA SDT R4 turbofan fan
- Run: `run-ffa59c9fd3cd` / `PASS`
- Surfaces: `141`
- Full model snapshot: `model_snapshots/public-nasa-sdt-r4-turbofan-fan/public-nasa-sdt-r4-turbofan-fan.snapshot.png`
- Exact generation JSON: `model_snapshots/public-nasa-sdt-r4-turbofan-fan/public-nasa-sdt-r4-turbofan-fan.generation.json`
- Exports: `{"manifest": "model_snapshots/public-nasa-sdt-r4-turbofan-fan/public-nasa-sdt-r4-turbofan-fan.manifest.json", "obj": "model_snapshots/public-nasa-sdt-r4-turbofan-fan/public-nasa-sdt-r4-turbofan-fan.obj", "step": "model_snapshots/public-nasa-sdt-r4-turbofan-fan/public-nasa-sdt-r4-turbofan-fan.step", "stl": "model_snapshots/public-nasa-sdt-r4-turbofan-fan/public-nasa-sdt-r4-turbofan-fan.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "fan_or_blower",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 22,
    "inlet_radius_mm": 81,
    "exit_radius_mm": 279.4,
    "inlet_blade_height_mm": 198.4,
    "outlet_blade_height_mm": 190,
    "hub_curve_height_mm": 140,
    "mounting_bore_radius_mm": 33,
    "blade_wrap_deg": 86,
    "blade_lean_deg": 24,
    "leading_edge_lean_deg": 14,
    "trailing_edge_lean_deg": -12,
    "leading_edge_sweep_mm": 18,
    "trailing_edge_sweep_mm": -22,
    "blade_thickness_mm": 8,
    "root_fillet_radius_mm": 2.4,
    "leading_edge_radius_mm": 1.2,
    "trailing_edge_radius_mm": 0.8,
    "tip_edge_radius_mm": 0.8,
    "hub_wall_thickness_mm": 10,
    "hub_bottom_thickness_mm": 14,
    "hub_top_cap_thickness_mm": 5,
    "hub_chamfer_radius_mm": 1.5,
    "hood_wall_thickness_mm": 4,
    "hood_chamfer_radius_mm": 1
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          81,
          140
        ],
        [
          82.2,
          112
        ],
        [
          84,
          84
        ],
        [
          85.5,
          54
        ],
        [
          86.4,
          24
        ],
        [
          87,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          279.4,
          141
        ],
        [
          279.2,
          113
        ],
        [
          278.9,
          85
        ],
        [
          278.6,
          55
        ],
        [
          278.3,
          25
        ],
        [
          278,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.15,
            -8
          ],
          [
            0.45,
            -42
          ],
          [
            0.75,
            -72
          ],
          [
            1,
            -86
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            14
          ],
          [
            0.35,
            30
          ],
          [
            0.7,
            20
          ],
          [
            1,
            -12
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            -0.08
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0.11
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0.1
          ],
          [
            0.5,
            0
          ],
          [
            1,
            -0.12
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            8
          ],
          [
            0.35,
            7.2
          ],
          [
            0.7,
            5.2
          ],
          [
            1,
            3.5
          ]
        ]
      }
    }
  }
}
```

### `public-rr-ultrafan-cti-fan`

Updated in this pass: hub_profile is no longer near-cylindrical; it uses a nose-ogive control polygon from small nose radius to large aft hub radius. Extra hub-only and R-Z profile snapshots are included.

- Name: Public RR UltraFan CTi fan
- Run: `run-caf0f3b01b09` / `PASS`
- Surfaces: `117`
- Full model snapshot: `model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.snapshot.png`
- Hub-only snapshot: `model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.hub.snapshot.png`
- Hub profile snapshot: `model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.hub-profile.png`
- Exact generation JSON: `model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.generation.json`
- Exports: `{"manifest": "model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.manifest.json", "obj": "model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.obj", "step": "model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.step", "stl": "model_snapshots/public-rr-ultrafan-cti-fan/public-rr-ultrafan-cti-fan.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "fan_or_blower",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 18,
    "inlet_radius_mm": 533,
    "exit_radius_mm": 1778,
    "inlet_blade_height_mm": 1245,
    "outlet_blade_height_mm": 1170,
    "hub_curve_height_mm": 850,
    "mounting_bore_radius_mm": 90,
    "blade_wrap_deg": 92,
    "blade_lean_deg": 28,
    "leading_edge_lean_deg": 16,
    "trailing_edge_lean_deg": -14,
    "leading_edge_sweep_mm": 90,
    "trailing_edge_sweep_mm": -120,
    "blade_thickness_mm": 45,
    "root_fillet_radius_mm": 14,
    "leading_edge_radius_mm": 7,
    "trailing_edge_radius_mm": 4,
    "tip_edge_radius_mm": 4,
    "hub_wall_thickness_mm": 55,
    "hub_bottom_thickness_mm": 75,
    "hub_top_cap_thickness_mm": 24,
    "hub_chamfer_radius_mm": 8,
    "hood_wall_thickness_mm": 12,
    "hood_chamfer_radius_mm": 3
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          140,
          850
        ],
        [
          255,
          790
        ],
        [
          430,
          650
        ],
        [
          530,
          430
        ],
        [
          575,
          170
        ],
        [
          600,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          1778,
          851
        ],
        [
          1776,
          791
        ],
        [
          1773,
          651
        ],
        [
          1770,
          431
        ],
        [
          1765,
          171
        ],
        [
          1760,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.15,
            -10
          ],
          [
            0.45,
            -45
          ],
          [
            0.75,
            -78
          ],
          [
            1,
            -92
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            16
          ],
          [
            0.35,
            34
          ],
          [
            0.7,
            25
          ],
          [
            1,
            -14
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            -0.09
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0.12
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0.11
          ],
          [
            0.5,
            0
          ],
          [
            1,
            -0.14
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            45
          ],
          [
            0.35,
            37
          ],
          [
            0.7,
            24
          ],
          [
            1,
            16
          ]
        ]
      }
    }
  }
}
```

### `public-rr-ultrafan-ogv-ring`

- Name: Public RR UltraFan OGV ring
- Run: `run-0b28bbde026d` / `PASS`
- Surfaces: `278`
- Full model snapshot: `model_snapshots/public-rr-ultrafan-ogv-ring/public-rr-ultrafan-ogv-ring.snapshot.png`
- Exact generation JSON: `model_snapshots/public-rr-ultrafan-ogv-ring/public-rr-ultrafan-ogv-ring.generation.json`
- Exports: `{"manifest": "model_snapshots/public-rr-ultrafan-ogv-ring/public-rr-ultrafan-ogv-ring.manifest.json", "obj": "model_snapshots/public-rr-ultrafan-ogv-ring/public-rr-ultrafan-ogv-ring.obj", "step": "model_snapshots/public-rr-ultrafan-ogv-ring/public-rr-ultrafan-ogv-ring.step", "stl": "model_snapshots/public-rr-ultrafan-ogv-ring/public-rr-ultrafan-ogv-ring.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "closed",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "fan_or_blower",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 44,
    "inlet_radius_mm": 600,
    "exit_radius_mm": 1778,
    "inlet_blade_height_mm": 1178,
    "outlet_blade_height_mm": 1148,
    "hub_curve_height_mm": 520,
    "mounting_bore_radius_mm": 260,
    "blade_wrap_deg": 32,
    "blade_lean_deg": 3,
    "leading_edge_lean_deg": -8,
    "trailing_edge_lean_deg": 8,
    "leading_edge_sweep_mm": 25,
    "trailing_edge_sweep_mm": -35,
    "blade_thickness_mm": 28,
    "root_fillet_radius_mm": 9,
    "leading_edge_radius_mm": 4,
    "trailing_edge_radius_mm": 2.5,
    "tip_edge_radius_mm": 2.5,
    "hub_wall_thickness_mm": 40,
    "hub_bottom_thickness_mm": 55,
    "hub_top_cap_thickness_mm": 18,
    "hub_chamfer_radius_mm": 6,
    "hood_wall_thickness_mm": 18,
    "hood_chamfer_radius_mm": 5
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          600,
          520
        ],
        [
          603,
          416
        ],
        [
          608,
          312
        ],
        [
          612,
          205
        ],
        [
          616,
          90
        ],
        [
          620,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          1778,
          521
        ],
        [
          1776,
          417
        ],
        [
          1774,
          313
        ],
        [
          1772,
          206
        ],
        [
          1770,
          91
        ],
        [
          1768,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.25,
            5
          ],
          [
            0.6,
            19
          ],
          [
            1,
            32
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            -8
          ],
          [
            0.45,
            3
          ],
          [
            1,
            8
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            -0.025
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0.035
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0.04
          ],
          [
            0.5,
            0
          ],
          [
            1,
            -0.045
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            28
          ],
          [
            0.45,
            24
          ],
          [
            1,
            15
          ]
        ]
      }
    }
  }
}
```

### `public-liquid-rocket-turbopump-inducer`

Updated in this pass: hub_profile is a bullet/nose-ogive shaft instead of a cylinder. Extra hub-only and R-Z profile snapshots are included.

- Name: Public liquid rocket turbopump inducer
- Run: `run-913ddefa68d5` / `PASS`
- Surfaces: `27`
- Full model snapshot: `model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.snapshot.png`
- Hub-only snapshot: `model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.hub.snapshot.png`
- Hub profile snapshot: `model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.hub-profile.png`
- Exact generation JSON: `model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.generation.json`
- Exports: `{"manifest": "model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.manifest.json", "obj": "model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.obj", "step": "model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.step", "stl": "model_snapshots/public-liquid-rocket-turbopump-inducer/public-liquid-rocket-turbopump-inducer.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 3,
    "inlet_radius_mm": 35,
    "exit_radius_mm": 72.5,
    "inlet_blade_height_mm": 35,
    "outlet_blade_height_mm": 32.5,
    "hub_curve_height_mm": 120,
    "mounting_bore_radius_mm": 4,
    "blade_wrap_deg": 230,
    "blade_lean_deg": 10,
    "leading_edge_lean_deg": 4,
    "trailing_edge_lean_deg": 14,
    "leading_edge_sweep_mm": 10,
    "trailing_edge_sweep_mm": -8,
    "blade_thickness_mm": 2.5,
    "root_fillet_radius_mm": 0.8,
    "leading_edge_radius_mm": 0.35,
    "trailing_edge_radius_mm": 0.25,
    "tip_edge_radius_mm": 0.25,
    "hub_wall_thickness_mm": 4,
    "hub_bottom_thickness_mm": 6,
    "hub_top_cap_thickness_mm": 2,
    "hub_chamfer_radius_mm": 0.6,
    "hood_wall_thickness_mm": 2,
    "hood_chamfer_radius_mm": 0.5
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          10,
          120
        ],
        [
          15,
          110
        ],
        [
          25,
          92
        ],
        [
          34,
          62
        ],
        [
          39,
          26
        ],
        [
          42,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          70,
          121
        ],
        [
          70.5,
          111
        ],
        [
          71,
          93
        ],
        [
          71.5,
          63
        ],
        [
          72,
          27
        ],
        [
          72.5,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.25,
            -55
          ],
          [
            0.6,
            -150
          ],
          [
            1,
            -230
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            4
          ],
          [
            0.5,
            9
          ],
          [
            1,
            14
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            -0.12
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0.16
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0.1
          ],
          [
            0.5,
            0
          ],
          [
            1,
            -0.14
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            2.5
          ],
          [
            0.45,
            2.1
          ],
          [
            1,
            1.2
          ]
        ]
      }
    }
  }
}
```

### `public-nasa-sr7l-propfan`

- Name: Public NASA SR-7L propfan
- Run: `run-ac63c0a284bc` / `PASS`
- Surfaces: `57`
- Full model snapshot: `model_snapshots/public-nasa-sr7l-propfan/public-nasa-sr7l-propfan.snapshot.png`
- Exact generation JSON: `model_snapshots/public-nasa-sr7l-propfan/public-nasa-sr7l-propfan.generation.json`
- Exports: `{"manifest": "model_snapshots/public-nasa-sr7l-propfan/public-nasa-sr7l-propfan.manifest.json", "obj": "model_snapshots/public-nasa-sr7l-propfan/public-nasa-sr7l-propfan.obj", "step": "model_snapshots/public-nasa-sr7l-propfan/public-nasa-sr7l-propfan.step", "stl": "model_snapshots/public-nasa-sr7l-propfan/public-nasa-sr7l-propfan.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "fan_or_blower",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 8,
    "inlet_radius_mm": 220,
    "exit_radius_mm": 1370,
    "inlet_blade_height_mm": 1150,
    "outlet_blade_height_mm": 1110,
    "hub_curve_height_mm": 500,
    "mounting_bore_radius_mm": 95,
    "blade_wrap_deg": 130,
    "blade_lean_deg": 36,
    "leading_edge_lean_deg": 20,
    "trailing_edge_lean_deg": -8,
    "leading_edge_sweep_mm": 120,
    "trailing_edge_sweep_mm": -160,
    "blade_thickness_mm": 20,
    "root_fillet_radius_mm": 6,
    "leading_edge_radius_mm": 3,
    "trailing_edge_radius_mm": 1.5,
    "tip_edge_radius_mm": 1.5,
    "hub_wall_thickness_mm": 24,
    "hub_bottom_thickness_mm": 35,
    "hub_top_cap_thickness_mm": 10,
    "hub_chamfer_radius_mm": 4,
    "hood_wall_thickness_mm": 8,
    "hood_chamfer_radius_mm": 2
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          220,
          500
        ],
        [
          225,
          400
        ],
        [
          235,
          300
        ],
        [
          245,
          190
        ],
        [
          255,
          80
        ],
        [
          260,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          1370,
          501
        ],
        [
          1369,
          401
        ],
        [
          1368,
          301
        ],
        [
          1367,
          191
        ],
        [
          1366,
          81
        ],
        [
          1365,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.2,
            -15
          ],
          [
            0.55,
            -70
          ],
          [
            0.85,
            -115
          ],
          [
            1,
            -130
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            20
          ],
          [
            0.4,
            42
          ],
          [
            0.75,
            30
          ],
          [
            1,
            -8
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            -0.18
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0.22
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0.16
          ],
          [
            0.5,
            0
          ],
          [
            1,
            -0.22
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            20
          ],
          [
            0.35,
            16
          ],
          [
            0.7,
            10
          ],
          [
            1,
            6
          ]
        ]
      }
    }
  }
}
```

### `reference-spur-gear-tooth-ring`

Mechanical analogy only. It uses blade_count as tooth count and radial blades as tooth proxies; it is not an involute gear solver.

- Name: Reference spur gear tooth ring
- Run: `run-c54c8ed5b0c8` / `PASS`
- Surfaces: `153`
- Full model snapshot: `model_snapshots/reference-spur-gear-tooth-ring/reference-spur-gear-tooth-ring.snapshot.png`
- Exact generation JSON: `model_snapshots/reference-spur-gear-tooth-ring/reference-spur-gear-tooth-ring.generation.json`
- Exports: `{"manifest": "model_snapshots/reference-spur-gear-tooth-ring/reference-spur-gear-tooth-ring.manifest.json", "obj": "model_snapshots/reference-spur-gear-tooth-ring/reference-spur-gear-tooth-ring.obj", "step": "model_snapshots/reference-spur-gear-tooth-ring/reference-spur-gear-tooth-ring.step", "stl": "model_snapshots/reference-spur-gear-tooth-ring/reference-spur-gear-tooth-ring.stl"}`

```json
{
  "facets": {
    "flow_topology": "radial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 24,
    "inlet_radius_mm": 36,
    "exit_radius_mm": 48,
    "inlet_blade_height_mm": 14,
    "outlet_blade_height_mm": 14,
    "hub_curve_height_mm": 18,
    "mounting_bore_radius_mm": 12,
    "blade_wrap_deg": 4,
    "blade_lean_deg": 0,
    "leading_edge_lean_deg": 0,
    "trailing_edge_lean_deg": 0,
    "leading_edge_sweep_mm": 0,
    "trailing_edge_sweep_mm": 0,
    "blade_thickness_mm": 4,
    "root_fillet_radius_mm": 0.8,
    "leading_edge_radius_mm": 0.5,
    "trailing_edge_radius_mm": 0.5,
    "tip_edge_radius_mm": 0.5,
    "hub_wall_thickness_mm": 6,
    "hub_bottom_thickness_mm": 6,
    "hub_top_cap_thickness_mm": 3,
    "hub_chamfer_radius_mm": 0.8,
    "hood_wall_thickness_mm": 1,
    "hood_chamfer_radius_mm": 0.5
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          28,
          18
        ],
        [
          32,
          16
        ],
        [
          36,
          12
        ],
        [
          38,
          8
        ],
        [
          39,
          4
        ],
        [
          40,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          48,
          19
        ],
        [
          48,
          17
        ],
        [
          48,
          13
        ],
        [
          48,
          9
        ],
        [
          48,
          5
        ],
        [
          48,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.3,
            -1
          ],
          [
            0.7,
            -3
          ],
          [
            1,
            -4
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            4
          ],
          [
            0.5,
            4
          ],
          [
            1,
            3.2
          ]
        ]
      }
    }
  }
}
```

### `reference-axial-turbine-rotor`

Mechanical analogy only. It uses an axial bladed-disk topology and twist curves; it is not validated turbine aerodynamics.

- Name: Reference axial turbine rotor
- Run: `run-2e89991e13ce` / `PASS`
- Surfaces: `333`
- Full model snapshot: `model_snapshots/reference-axial-turbine-rotor/reference-axial-turbine-rotor.snapshot.png`
- Exact generation JSON: `model_snapshots/reference-axial-turbine-rotor/reference-axial-turbine-rotor.generation.json`
- Exports: `{"manifest": "model_snapshots/reference-axial-turbine-rotor/reference-axial-turbine-rotor.manifest.json", "obj": "model_snapshots/reference-axial-turbine-rotor/reference-axial-turbine-rotor.obj", "step": "model_snapshots/reference-axial-turbine-rotor/reference-axial-turbine-rotor.step", "stl": "model_snapshots/reference-axial-turbine-rotor/reference-axial-turbine-rotor.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "compressor",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 54,
    "inlet_radius_mm": 155,
    "exit_radius_mm": 275,
    "inlet_blade_height_mm": 120,
    "outlet_blade_height_mm": 105,
    "hub_curve_height_mm": 95,
    "mounting_bore_radius_mm": 60,
    "blade_wrap_deg": 48,
    "blade_lean_deg": 18,
    "leading_edge_lean_deg": 12,
    "trailing_edge_lean_deg": -18,
    "leading_edge_sweep_mm": 12,
    "trailing_edge_sweep_mm": -18,
    "blade_thickness_mm": 4,
    "root_fillet_radius_mm": 1.5,
    "leading_edge_radius_mm": 0.7,
    "trailing_edge_radius_mm": 0.4,
    "tip_edge_radius_mm": 0.4,
    "hub_wall_thickness_mm": 8,
    "hub_bottom_thickness_mm": 12,
    "hub_top_cap_thickness_mm": 4,
    "hub_chamfer_radius_mm": 1.2,
    "hood_wall_thickness_mm": 3,
    "hood_chamfer_radius_mm": 0.8
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          155,
          95
        ],
        [
          158,
          76
        ],
        [
          160,
          57
        ],
        [
          164,
          38
        ],
        [
          168,
          18
        ],
        [
          170,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          275,
          96
        ],
        [
          274,
          77
        ],
        [
          273,
          58
        ],
        [
          272,
          39
        ],
        [
          271,
          19
        ],
        [
          270,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.2,
            8
          ],
          [
            0.55,
            28
          ],
          [
            0.85,
            42
          ],
          [
            1,
            48
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            12
          ],
          [
            0.45,
            24
          ],
          [
            1,
            -18
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            -0.05
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0.07
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0.08
          ],
          [
            0.5,
            0
          ],
          [
            1,
            -0.09
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            4
          ],
          [
            0.45,
            3.4
          ],
          [
            1,
            2
          ]
        ]
      }
    }
  }
}
```

### `reference-double-start-worm`

Mechanical analogy only. Current V0.7 schema has blade_count min 2, so this is a double-start worm proxy rather than a true single-start worm.

- Name: Reference double-start worm
- Run: `run-740be69b4400` / `PASS`
- Surfaces: `21`
- Full model snapshot: `model_snapshots/reference-double-start-worm/reference-double-start-worm.snapshot.png`
- Exact generation JSON: `model_snapshots/reference-double-start-worm/reference-double-start-worm.generation.json`
- Exports: `{"manifest": "model_snapshots/reference-double-start-worm/reference-double-start-worm.manifest.json", "obj": "model_snapshots/reference-double-start-worm/reference-double-start-worm.obj", "step": "model_snapshots/reference-double-start-worm/reference-double-start-worm.step", "stl": "model_snapshots/reference-double-start-worm/reference-double-start-worm.stl"}`

```json
{
  "facets": {
    "flow_topology": "axial",
    "shroud_topology": "open",
    "suction_topology": "single_suction",
    "blade_exit_geometry": "backward_curved",
    "working_domain": "pump",
    "passage_topology": "throughflow_bladed_channel"
  },
  "parameters": {
    "blade_count": 2,
    "inlet_radius_mm": 18,
    "exit_radius_mm": 45,
    "inlet_blade_height_mm": 27,
    "outlet_blade_height_mm": 27,
    "hub_curve_height_mm": 160,
    "mounting_bore_radius_mm": 5,
    "blade_wrap_deg": 720,
    "blade_lean_deg": 0,
    "leading_edge_lean_deg": 0,
    "trailing_edge_lean_deg": 0,
    "leading_edge_sweep_mm": 0,
    "trailing_edge_sweep_mm": 0,
    "blade_thickness_mm": 5,
    "root_fillet_radius_mm": 1,
    "leading_edge_radius_mm": 0.5,
    "trailing_edge_radius_mm": 0.5,
    "tip_edge_radius_mm": 0.5,
    "hub_wall_thickness_mm": 5,
    "hub_bottom_thickness_mm": 7,
    "hub_top_cap_thickness_mm": 3,
    "hub_chamfer_radius_mm": 0.8,
    "hood_wall_thickness_mm": 1,
    "hood_chamfer_radius_mm": 0.5
  },
  "profile_overrides": {
    "hub_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          18,
          160
        ],
        [
          18,
          128
        ],
        [
          18,
          96
        ],
        [
          18,
          64
        ],
        [
          18,
          32
        ],
        [
          18,
          0
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    },
    "tip_or_shroud_profile": {
      "kind": "nurbs_curve",
      "degree": 3,
      "coordinate_system": "rz_meridional_mm",
      "control_points": [
        [
          45,
          161
        ],
        [
          45,
          129
        ],
        [
          45,
          97
        ],
        [
          45,
          65
        ],
        [
          45,
          33
        ],
        [
          45,
          1
        ]
      ],
      "weights": [
        1,
        1,
        1,
        1,
        1,
        1
      ],
      "knots": [
        0,
        0,
        0,
        0,
        0.333333,
        0.666667,
        1,
        1,
        1,
        1
      ]
    }
  },
  "curve_overrides": {
    "blade_mean": {
      "theta_center_u_curve": {
        "coordinate_system": "u_theta_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.25,
            -180
          ],
          [
            0.5,
            -360
          ],
          [
            0.75,
            -540
          ],
          [
            1,
            -720
          ]
        ]
      },
      "span_lean_u_curve": {
        "coordinate_system": "u_lean_deg",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0
          ]
        ]
      }
    },
    "blade_edges": {
      "leading_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0
          ]
        ]
      },
      "trailing_edge_sweep_v_curve": {
        "coordinate_system": "v_support_u_offset",
        "control_points": [
          [
            0,
            0
          ],
          [
            0.5,
            0
          ],
          [
            1,
            0
          ]
        ]
      }
    },
    "thickness": {
      "thickness_u_curve": {
        "coordinate_system": "u_thickness_mm",
        "control_points": [
          [
            0,
            5
          ],
          [
            0.5,
            5
          ],
          [
            1,
            5
          ]
        ]
      }
    }
  }
}
```
