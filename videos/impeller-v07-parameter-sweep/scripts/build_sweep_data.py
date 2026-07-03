from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT / "data"
ASSET_DIR = PROJECT / "assets"
DURATION_SECONDS = 72
SAMPLES_PER_SEGMENT = 5
MAX_U_SAMPLES = 17
MAX_V_SAMPLES = 11

CASE_ORDER = [
    "axisymmetric-nurbs-open-throughflow",
    "public-nasa-rotor67-axial-blisk",
    "public-nasa-stage37-stator-ring",
    "public-nasa-sdt-r4-turbofan-fan",
    "public-rr-ultrafan-cti-fan",
    "public-rr-ultrafan-ogv-ring",
    "public-liquid-rocket-turbopump-inducer",
    "public-nasa-sr7l-propfan",
    "reference-spur-gear-tooth-ring",
    "reference-axial-turbine-rotor",
    "reference-double-start-worm",
]

PARAMETER_KEYS = [
    "blade_count",
    "inlet_radius_mm",
    "exit_radius_mm",
    "inlet_blade_height_mm",
    "outlet_blade_height_mm",
    "hub_curve_height_mm",
    "mounting_bore_radius_mm",
    "blade_wrap_deg",
    "blade_lean_deg",
    "leading_edge_lean_deg",
    "trailing_edge_lean_deg",
    "leading_edge_sweep_mm",
    "trailing_edge_sweep_mm",
    "blade_thickness_mm",
    "root_fillet_radius_mm",
    "leading_edge_radius_mm",
    "trailing_edge_radius_mm",
    "tip_edge_radius_mm",
]

CURVE_SAMPLE_T = {
    "theta_center_u_curve": [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0],
    "span_lean_u_curve": [0.0, 0.25, 0.5, 0.75, 1.0],
    "leading_edge_sweep_v_curve": [0.0, 0.25, 0.5, 0.75, 1.0],
    "trailing_edge_sweep_v_curve": [0.0, 0.25, 0.5, 0.75, 1.0],
    "thickness_u_curve": [0.0, 0.167, 0.333, 0.5, 0.667, 0.833, 1.0],
}


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from part_rule_synthesis.impeller_transition_policies import resolve_transition_policies
    from part_rule_synthesis.service import (
        RuleSynthesisService,
        _bind_parameters,
        _geometry_metadata,
        _normalize_geometry_stage,
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    (PROJECT / "renders").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "videos" / "impeller-v03-parameter-sweep" / "assets" / "gsap.min.js", ASSET_DIR / "gsap.min.js")

    cases = load_frontend_cases()
    snapshots = []
    with TemporaryDirectory() as temp_root:
        service = RuleSynthesisService(Path(temp_root) / "runs")
        for segment_index, (start, end) in enumerate(zip(cases, cases[1:])):
            for sample_index in range(SAMPLES_PER_SEGMENT):
                raw_t = sample_index / SAMPLES_PER_SEGMENT
                payload_case = interpolated_case(start, end, smoothstep(raw_t))
                snapshots.append(
                    build_snapshot(
                        service,
                        payload_case,
                        segment_index=segment_index,
                        raw_t=raw_t,
                        resolve_transition_policies=resolve_transition_policies,
                        bind_parameters=_bind_parameters,
                        geometry_metadata=_geometry_metadata,
                        normalize_geometry_stage=_normalize_geometry_stage,
                    )
                )
        snapshots.append(
            build_snapshot(
                service,
                cases[-1],
                segment_index=len(cases) - 2,
                raw_t=1.0,
                resolve_transition_policies=resolve_transition_policies,
                bind_parameters=_bind_parameters,
                geometry_metadata=_geometry_metadata,
                normalize_geometry_stage=_normalize_geometry_stage,
            )
        )

    parameter_ranges = build_parameter_ranges(snapshots)
    payload = {
        "schema": "impeller_v0_7_surface_graph_native_sweep_video",
        "duration_seconds": DURATION_SECONDS,
        "fps": 60,
        "sample_count": len(snapshots),
        "samples_per_segment": SAMPLES_PER_SEGMENT,
        "source": {
            "constructor": "AxisymmetricThroughflowRadialBladedImpeller",
            "dsl_version": "0.7",
            "geometry_source": "current frontend presets -> RuleSynthesisService geometry_metadata -> geometry.surface_graph.surfaces[].uv_grid",
            "display_note": "Each video sample is an actual constructor surface_graph snapshot. uv_grid is uniformly decimated only for video payload size; no procedural geometry is created in the video layer.",
        },
        "parameter_keys": PARAMETER_KEYS,
        "parameter_ranges": parameter_ranges,
        "cases": [{"id": case["id"], "name": case["name"], "preset_id": case["preset_id"]} for case in cases],
        "snapshots": snapshots,
    }
    out = DATA_DIR / "impeller_v07_sweep_data.js"
    out.write_text(
        "window.IMPELLER_V07_SWEEP_DATA = "
        + json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {out.relative_to(ROOT)}")
    print(f"Cases: {len(cases)}; snapshots: {len(snapshots)}")
    print(f"BLISK cases: {[case['id'] for case in cases if 'blisk' in case['id']]}")


def load_frontend_cases() -> list[dict[str, Any]]:
    js = f"""
import {{ presets, buildInstantiatePayload }} from './frontend/src/appModel.js';
const ids = {json.dumps(CASE_ORDER)};
const cases = ids.map((id) => {{
  const preset = presets.find((item) => item.id === id);
  if (!preset) throw new Error(`missing preset ${{id}}`);
  return {{
    id: preset.id,
    name: preset.name,
    preset_id: preset.presetId,
    facets: preset.facets,
    tags: preset.tags || [],
    payload: buildInstantiatePayload(
      preset.parameters,
      preset.profileOverrides || null,
      preset.curveOverrides || null,
      null,
      'edge_closures'
    ),
  }};
}});
console.log(JSON.stringify(cases));
"""
    raw = subprocess.check_output(["node", "--input-type=module", "-e", js], cwd=ROOT, text=True)
    return json.loads(raw)


def interpolated_case(start: dict[str, Any], end: dict[str, Any], t: float) -> dict[str, Any]:
    payload = {
        "parameters": interpolate_parameters(start["payload"]["parameters"], end["payload"]["parameters"], t),
        "geometry_stage": "edge_closures",
    }
    profile = interpolate_profile_overrides(
        start["payload"].get("profile_overrides"),
        end["payload"].get("profile_overrides"),
        t,
    )
    if profile:
        payload["profile_overrides"] = profile
    curves = interpolate_curve_overrides(
        start["payload"].get("curve_overrides"),
        end["payload"].get("curve_overrides"),
        t,
    )
    if curves:
        payload["curve_overrides"] = curves
    facet_source = start if t < 0.5 else end
    return {
        "id": f"{start['id']}__to__{end['id']}",
        "name": f"{start['name']} -> {end['name']}",
        "preset_id": facet_source["preset_id"],
        "facets": facet_source["facets"],
        "tags": sorted(set(start.get("tags", [])) | set(end.get("tags", []))),
        "payload": payload,
        "from": {"id": start["id"], "name": start["name"]},
        "to": {"id": end["id"], "name": end["name"]},
    }


def build_snapshot(
    service: Any,
    case: dict[str, Any],
    *,
    segment_index: int,
    raw_t: float,
    resolve_transition_policies: Any,
    bind_parameters: Any,
    geometry_metadata: Any,
    normalize_geometry_stage: Any,
) -> dict[str, Any]:
    engine = service.synthesize("impeller", case["preset_id"], case["facets"])
    dsl = service.engines[engine.engine_id]
    payload = case["payload"]
    bound = bind_parameters(dsl, payload.get("parameters", {}))
    edge_families = dsl.get("edge_families", {})
    transition_policies = resolve_transition_policies(edge_families, bound, payload.get("transition_overrides", {})) if edge_families else None
    geometry = geometry_metadata(
        dsl["part_family"],
        bound,
        dsl.get("facets", {}),
        profile_overrides=payload.get("profile_overrides", {}),
        curve_overrides=payload.get("curve_overrides", {}),
        geometry_stage=normalize_geometry_stage(payload.get("geometry_stage", "edge_closures")),
        dsl_context=dsl,
        edge_families=edge_families,
        transition_policies=transition_policies,
    )
    surface_graph = geometry.get("surface_graph", {})
    surfaces, original_triangles, display_triangles = video_surfaces(surface_graph.get("surfaces", []))
    return {
        "id": case["id"],
        "name": case["name"],
        "from": case.get("from", {"id": case["id"], "name": case["name"]}),
        "to": case.get("to", {"id": case["id"], "name": case["name"]}),
        "preset_id": case["preset_id"],
        "segment_index": segment_index,
        "segment_t": round(raw_t, 4),
        "status": geometry.get("validity", {}).get("status", "PASS"),
        "facets": dsl.get("facets", {}),
        "parameters": {key: round_float(bound.get(key, 0.0)) for key in PARAMETER_KEYS},
        "derived": derived_metrics(bound, dsl.get("facets", {})),
        "stats": {
            "surface_count": len(surface_graph.get("surfaces", [])),
            "display_surface_count": len(surfaces),
            "source_triangle_count": original_triangles,
            "display_triangle_count": display_triangles,
        },
        "surfaces": surfaces,
    }


def video_surfaces(source_surfaces: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    out = []
    original_triangles = 0
    display_triangles = 0
    for surface in source_surfaces:
        grid = surface.get("uv_grid") or []
        if len(grid) < 2 or len(grid[0]) < 2:
            continue
        original_triangles += grid_triangle_count(grid)
        sampled = decimate_grid(grid, MAX_U_SAMPLES, MAX_V_SAMPLES)
        display_triangles += grid_triangle_count(sampled)
        out.append(
            {
                "id": surface.get("id") or surface.get("surface_graph_id"),
                "kind": surface.get("kind", ""),
                "role": surface.get("role", ""),
                "cfd_role": surface.get("cfd_role", ""),
                "display": surface.get("display", {}),
                "uv_grid": round_grid(sampled),
            }
        )
    return out, original_triangles, display_triangles


def decimate_grid(grid: list[list[list[float]]], max_u: int, max_v: int) -> list[list[list[float]]]:
    u_indices = sample_indices(len(grid), max_u)
    v_indices = sample_indices(len(grid[0]), max_v)
    return [[grid[u][v] for v in v_indices] for u in u_indices]


def sample_indices(count: int, limit: int) -> list[int]:
    if count <= limit:
        return list(range(count))
    return sorted({round(index * (count - 1) / (limit - 1)) for index in range(limit)})


def grid_triangle_count(grid: list[list[Any]]) -> int:
    if len(grid) < 2 or len(grid[0]) < 2:
        return 0
    return (len(grid) - 1) * (len(grid[0]) - 1) * 2


def interpolate_parameters(a: dict[str, Any], b: dict[str, Any], t: float) -> dict[str, float]:
    keys = set(a) | set(b) | set(PARAMETER_KEYS)
    return {key: round_float(lerp(float(a.get(key, b.get(key, 0))), float(b.get(key, a.get(key, 0))), t)) for key in keys}


def interpolate_profile_overrides(a: dict[str, Any] | None, b: dict[str, Any] | None, t: float) -> dict[str, Any] | None:
    if not a and not b:
        return None
    if not a or not b:
        return b if t >= 0.98 else a if t <= 0.02 else None
    result = {}
    for key in ("hub_profile", "tip_or_shroud_profile"):
        if key not in a or key not in b:
            continue
        left = a[key]
        right = b[key]
        points = [
            [round_float(lerp(lp[0], rp[0], t)), round_float(lerp(lp[1], rp[1], t))]
            for lp, rp in zip(left.get("control_points", []), right.get("control_points", []))
        ]
        degree = min(int(left.get("degree", right.get("degree", 3))), len(points) - 1)
        result[key] = {
            "kind": "nurbs_curve",
            "degree": degree,
            "coordinate_system": left.get("coordinate_system", "rz_meridional_mm"),
            "control_points": points,
            "weights": [1 for _ in points],
            "knots": clamped_uniform_knots(len(points), degree),
        }
    return result or None


def interpolate_curve_overrides(a: dict[str, Any] | None, b: dict[str, Any] | None, t: float) -> dict[str, Any] | None:
    if not a and not b:
        return None
    if not a or not b:
        return b if t >= 0.98 else a if t <= 0.02 else None
    result: dict[str, Any] = {"blade_mean": {}, "blade_edges": {}, "thickness": {}}
    curve_specs = [
        ("blade_mean", "theta_center_u_curve"),
        ("blade_mean", "span_lean_u_curve"),
        ("blade_edges", "leading_edge_sweep_v_curve"),
        ("blade_edges", "trailing_edge_sweep_v_curve"),
        ("thickness", "thickness_u_curve"),
    ]
    for group, curve_id in curve_specs:
        left = a.get(group, {}).get(curve_id)
        right = b.get(group, {}).get(curve_id)
        if not left or not right:
            continue
        ts = CURVE_SAMPLE_T[curve_id]
        points = [[x, round_float(lerp(curve_value(left, x), curve_value(right, x), t))] for x in ts]
        result[group][curve_id] = {
            "coordinate_system": left.get("coordinate_system", right.get("coordinate_system")),
            "control_points": points,
        }
    return {group: curves for group, curves in result.items() if curves} or None


def curve_value(curve: dict[str, Any], t: float) -> float:
    points = curve.get("control_points", [])
    if not points:
        return 0.0
    if t <= points[0][0]:
        return float(points[0][1])
    for left, right in zip(points, points[1:]):
        if t <= right[0]:
            span = max(float(right[0]) - float(left[0]), 1e-9)
            ratio = (t - float(left[0])) / span
            return lerp(float(left[1]), float(right[1]), ratio)
    return float(points[-1][1])


def clamped_uniform_knots(control_point_count: int, degree: int) -> list[float]:
    interior_count = control_point_count - degree - 1
    knots = [0.0] * (degree + 1)
    for index in range(1, interior_count + 1):
        knots.append(round_float(index / (interior_count + 1)))
    knots.extend([1.0] * (degree + 1))
    return knots


def derived_metrics(parameters: dict[str, Any], facets: dict[str, Any]) -> dict[str, Any]:
    exit_radius = float(parameters.get("exit_radius_mm", 0.0))
    height = max(
        float(parameters.get("hub_curve_height_mm", 0.0)),
        float(parameters.get("inlet_blade_height_mm", 0.0)),
        float(parameters.get("outlet_blade_height_mm", 0.0)),
    )
    return {
        "diameter_mm": round_float(exit_radius * 2),
        "height_mm": round_float(height),
        "flow_topology": facets.get("flow_topology", ""),
        "shroud_topology": facets.get("shroud_topology", ""),
        "working_domain": facets.get("working_domain", ""),
    }


def build_parameter_ranges(snapshots: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    ranges: dict[str, dict[str, float]] = {}
    for key in PARAMETER_KEYS:
        values = [float(snapshot["parameters"].get(key, 0.0)) for snapshot in snapshots]
        ranges[key] = {"min": min(values), "max": max(values)}
    return ranges


def round_grid(grid: list[list[list[float]]]) -> list[list[list[float]]]:
    return [[[round_float(point[0]), round_float(point[1]), round_float(point[2])] for point in row] for row in grid]


def round_float(value: Any) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        return 0.0
    rounded = round(parsed, 5)
    return 0.0 if rounded == -0.0 else rounded


def smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


if __name__ == "__main__":
    main()
