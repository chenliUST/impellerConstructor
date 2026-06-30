from __future__ import annotations

import argparse
import csv
import json
import math
import multiprocessing as mp
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_kernel import build_impeller_geometry
from part_rule_synthesis.impeller_taxonomy import IMPELLER_FACET_AXES, IMPELLER_PRESETS
from part_rule_synthesis.service import RuleSynthesisService


DEFAULT_OUT_DIR = PROJECT_ROOT / "runs" / "impeller_parameter_experiment"
RANDOM_SEED = 20260629


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic impeller parameter coverage experiments.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--random-cases", type=int, default=180)
    parser.add_argument("--cad-limit", type=int, default=90)
    parser.add_argument("--cad-timeout-sec", type=float, default=25.0)
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = _dedupe_cases(
        _preset_cases()
        + _facet_matrix_cases()
        + _one_factor_stress_cases()
        + _random_cases(args.random_cases)
    )

    results = [_run_kernel_case(case) for case in cases]
    summary = _summarize(results, args)
    _write_outputs(out_dir, results, summary)

    _run_cad_subset(results, out_dir, args.cad_limit, args.cad_timeout_sec)

    summary = _summarize(results, args)
    _write_outputs(out_dir, results, summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _preset_cases() -> list[dict[str, Any]]:
    cases = []
    for preset_id, preset in IMPELLER_PRESETS.items():
        cases.append(
            {
                "case_id": f"preset::{preset_id}",
                "source": "preset_default",
                "preset_id": preset_id,
                "facets": dict(preset["facets"]),
                "parameters": dict(preset["parameters"]),
            }
        )
    return cases


def _facet_matrix_cases() -> list[dict[str, Any]]:
    cases = []
    working_domain = "pump"
    index = 0
    for flow in IMPELLER_FACET_AXES["flow_topology"]:
        for shroud in IMPELLER_FACET_AXES["shroud_topology"]:
            for suction in IMPELLER_FACET_AXES["suction_topology"]:
                for exit_geometry in IMPELLER_FACET_AXES["blade_exit_geometry"]:
                    for passage in IMPELLER_FACET_AXES["passage_topology"]:
                        facets = {
                            "flow_topology": flow,
                            "shroud_topology": shroud,
                            "suction_topology": suction,
                            "blade_exit_geometry": exit_geometry,
                            "working_domain": working_domain,
                            "passage_topology": passage,
                        }
                        cases.append(
                            {
                                "case_id": f"facet_matrix::{index:03d}",
                                "source": "facet_matrix",
                                "preset_id": "radial_open_backward_single_reference",
                                "facets": facets,
                                "parameters": _canonical_parameters(flow, exit_geometry, passage),
                            }
                        )
                        index += 1
    return cases


def _one_factor_stress_cases() -> list[dict[str, Any]]:
    variants: list[tuple[str, dict[str, float | int]]] = [
        ("blade_count_min", {"blade_count": 5}),
        ("blade_count_max", {"blade_count": 16}),
        ("thickness_min", {"blade_thickness_mm": 0.1}),
        ("thickness_80", {"blade_thickness_mm": 80.0}),
        ("thickness_150", {"blade_thickness_mm": 150.0}),
        ("thickness_max", {"blade_thickness_mm": 200.0}),
        ("beta_zero", {"inlet_blade_angle_deg": 0.0, "outlet_blade_angle_deg": 0.0}),
        ("beta_ninety", {"inlet_blade_angle_deg": 90.0, "outlet_blade_angle_deg": 90.0}),
        ("beta_cross_0_90", {"inlet_blade_angle_deg": 0.0, "outlet_blade_angle_deg": 90.0}),
        ("beta_cross_90_0", {"inlet_blade_angle_deg": 90.0, "outlet_blade_angle_deg": 0.0}),
        ("near_equal_radius", {"exit_radius_mm": "__inlet_plus_1__"}),
        ("reverse_radius", {"exit_radius_mm": "__inlet_times_0_85__"}),
        ("large_radius_ratio", {"exit_radius_mm": "__inlet_times_5__"}),
        ("short_span", {"inlet_blade_height_mm": 1.0, "outlet_blade_height_mm": 1.0}),
        ("tall_span", {"inlet_blade_height_mm": 1000.0, "outlet_blade_height_mm": 1000.0}),
        ("curve_gain_min", {"blade_curve_gain": 0.25}),
        ("curve_gain_max", {"blade_curve_gain": 4.0}),
        ("hub_curve_flat", {"hub_curve_height_mm": 0.0}),
        ("hub_curve_max", {"hub_curve_height_mm": 1000.0}),
        ("twist_positive_max", {"hub_twist_deg": 120.0, "tip_twist_deg": 160.0}),
        ("twist_negative_max", {"hub_twist_deg": -120.0, "tip_twist_deg": -160.0}),
        ("warp_max", {"hub_warp_mm": 300.0, "tip_warp_mm": 400.0}),
        (
            "twist_warp_max",
            {"hub_twist_deg": 120.0, "tip_twist_deg": 160.0, "hub_warp_mm": 300.0, "tip_warp_mm": 400.0},
        ),
        (
            "small_radius_high_warp",
            {"inlet_radius_mm": 20.0, "exit_radius_mm": 160.0, "hub_warp_mm": 300.0, "tip_warp_mm": 400.0},
        ),
        (
            "high_count_thick_small_radius",
            {"blade_count": 16, "inlet_radius_mm": 120.0, "exit_radius_mm": 240.0, "blade_thickness_mm": 200.0},
        ),
    ]

    cases = []
    for preset_id, preset in IMPELLER_PRESETS.items():
        for label, updates in variants:
            parameters = dict(preset["parameters"])
            for key, value in updates.items():
                if value == "__inlet_plus_1__":
                    parameters[key] = min(4000.0, float(parameters["inlet_radius_mm"]) + 1.0)
                elif value == "__inlet_times_0_85__":
                    parameters[key] = max(1.0, float(parameters["inlet_radius_mm"]) * 0.85)
                elif value == "__inlet_times_5__":
                    parameters[key] = min(4000.0, float(parameters["inlet_radius_mm"]) * 5.0)
                else:
                    parameters[key] = value
            cases.append(
                {
                    "case_id": f"stress::{preset_id}::{label}",
                    "source": "one_factor_stress",
                    "preset_id": preset_id,
                    "facets": dict(preset["facets"]),
                    "parameters": parameters,
                }
            )
    return cases


def _random_cases(count: int) -> list[dict[str, Any]]:
    rng = random.Random(RANDOM_SEED)
    cases = []
    for index in range(count):
        flow = rng.choice(IMPELLER_FACET_AXES["flow_topology"])
        shroud = rng.choice(IMPELLER_FACET_AXES["shroud_topology"])
        suction = rng.choice(IMPELLER_FACET_AXES["suction_topology"])
        exit_geometry = rng.choice(IMPELLER_FACET_AXES["blade_exit_geometry"])
        passage = rng.choice(IMPELLER_FACET_AXES["passage_topology"])
        domain = rng.choice(IMPELLER_FACET_AXES["working_domain"])
        inlet = rng.uniform(1.0, 900.0)
        if flow == "axial":
            ratio = rng.uniform(0.55, 1.65)
        else:
            ratio = rng.uniform(0.55, 4.4)
        parameters = {
            "blade_count": rng.randint(5, 16),
            "inlet_radius_mm": round(inlet, 3),
            "exit_radius_mm": round(min(4000.0, max(1.0, inlet * ratio)), 3),
            "inlet_blade_height_mm": round(rng.uniform(1.0, 1000.0), 3),
            "outlet_blade_height_mm": round(rng.uniform(1.0, 1000.0), 3),
            "inlet_blade_angle_deg": round(rng.uniform(0.0, 90.0), 3),
            "outlet_blade_angle_deg": round(rng.uniform(0.0, 90.0), 3),
            "blade_thickness_mm": round(rng.uniform(0.1, 200.0), 3),
            "blade_curve_gain": round(rng.uniform(0.25, 4.0), 3),
            "hub_curve_height_mm": round(rng.uniform(0.0, 1000.0), 3),
            "hub_twist_deg": round(rng.uniform(-120.0, 120.0), 3),
            "tip_twist_deg": round(rng.uniform(-160.0, 160.0), 3),
            "hub_warp_mm": round(rng.uniform(0.0, 300.0), 3),
            "tip_warp_mm": round(rng.uniform(0.0, 400.0), 3),
        }
        cases.append(
            {
                "case_id": f"random::{index:03d}",
                "source": "deterministic_random",
                "preset_id": "radial_open_backward_single_reference",
                "facets": {
                    "flow_topology": flow,
                    "shroud_topology": shroud,
                    "suction_topology": suction,
                    "blade_exit_geometry": exit_geometry,
                    "working_domain": domain,
                    "passage_topology": passage,
                },
                "parameters": parameters,
            }
        )
    return cases


def _canonical_parameters(flow: str, exit_geometry: str, passage: str) -> dict[str, float | int]:
    by_flow = {
        "radial": {
            "blade_count": 7,
            "inlet_radius_mm": 320.0,
            "exit_radius_mm": 1120.0,
            "inlet_blade_height_mm": 260.0,
            "outlet_blade_height_mm": 180.0,
            "hub_curve_height_mm": 160.0,
        },
        "mixed": {
            "blade_count": 8,
            "inlet_radius_mm": 330.0,
            "exit_radius_mm": 960.0,
            "inlet_blade_height_mm": 300.0,
            "outlet_blade_height_mm": 220.0,
            "hub_curve_height_mm": 220.0,
        },
        "axial": {
            "blade_count": 10,
            "inlet_radius_mm": 460.0,
            "exit_radius_mm": 640.0,
            "inlet_blade_height_mm": 280.0,
            "outlet_blade_height_mm": 260.0,
            "hub_curve_height_mm": 300.0,
        },
    }
    by_exit = {
        "backward_curved": {"inlet_blade_angle_deg": 20.0, "outlet_blade_angle_deg": 44.0, "blade_curve_gain": 1.4},
        "radial": {"inlet_blade_angle_deg": 24.0, "outlet_blade_angle_deg": 30.0, "blade_curve_gain": 1.2},
        "forward_curved": {"inlet_blade_angle_deg": 28.0, "outlet_blade_angle_deg": 68.0, "blade_curve_gain": 1.8},
    }
    parameters = {
        **by_flow[flow],
        **by_exit[exit_geometry],
        "blade_thickness_mm": 36.0,
        "hub_twist_deg": 0.0,
        "tip_twist_deg": 0.0,
        "hub_warp_mm": 0.0,
        "tip_warp_mm": 0.0,
    }
    if passage == "recessed_vortex":
        parameters["outlet_blade_height_mm"] = max(80.0, parameters["outlet_blade_height_mm"] * 0.72)
        parameters["hub_curve_height_mm"] = max(120.0, parameters["hub_curve_height_mm"] * 0.55)
    return parameters


def _dedupe_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique = []
    for case in cases:
        key = json.dumps({"facets": case["facets"], "parameters": case["parameters"]}, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(case)
    return unique


def _run_kernel_case(case: dict[str, Any]) -> dict[str, Any]:
    result = {
        "case_id": case["case_id"],
        "source": case["source"],
        "preset_id": case["preset_id"],
        "facets": case["facets"],
        "parameters": case["parameters"],
        "kernel_status": "NOT_RUN",
        "declared_validity_status": "NOT_RUN",
        "diagnostic_status": "NOT_RUN",
        "cad_status": "NOT_RUN",
        "issues": [],
        "metrics": {},
    }
    try:
        geometry = build_impeller_geometry(case["parameters"], case["facets"])
    except Exception as exc:
        result["kernel_status"] = "FAIL"
        result["declared_validity_status"] = "NOT_AVAILABLE"
        result["diagnostic_status"] = "FAIL"
        result["issues"].append(_issue("kernel_exception", "hard", str(exc)))
        return result

    result["kernel_status"] = "PASS"
    result["declared_validity_status"] = geometry.get("validity", {}).get("status", "UNKNOWN")
    if result["declared_validity_status"] != "PASS":
        result["issues"].append(_issue("declared_validity_failed", "hard", "Kernel validity report is not PASS."))

    diagnostic = _diagnose(case, geometry)
    result["issues"].extend(diagnostic["issues"])
    result["metrics"] = diagnostic["metrics"]
    hard_count = sum(1 for issue in result["issues"] if issue["severity"] == "hard")
    warning_count = sum(1 for issue in result["issues"] if issue["severity"] == "warning")
    result["diagnostic_status"] = "FAIL" if hard_count else ("WARN" if warning_count else "PASS")
    return result


def _diagnose(case: dict[str, Any], geometry: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    metrics: dict[str, Any] = {}
    facets = case["facets"]
    params = case["parameters"]

    graph = geometry["surface_graph"]
    blades = geometry["sampled_blades"]
    non_mirrored_blades = [blade for blade in blades if not blade["mirror_z"]]

    surface_metrics = _surface_quality_metrics(graph)
    metrics.update(surface_metrics)
    if surface_metrics["min_surface_cell_area_mm2"] <= 1e-5:
        issues.append(_issue("surface_cell_degenerate", "hard", "At least one parameter surface has a near-zero quad cell."))
    if surface_metrics["min_adjacent_normal_dot"] < -0.25:
        issues.append(_issue("surface_normal_flip", "hard", "Adjacent sampled surface cells reverse orientation."))
    if surface_metrics["max_surface_aspect_ratio"] > 250.0:
        issues.append(_issue("surface_aspect_extreme", "warning", "Some sampled surface cells are extremely stretched."))

    min_signed_radius = _minimum_signed_radius(geometry)
    metrics["min_signed_surface_radius_mm"] = round(min_signed_radius, 6)
    if min_signed_radius <= 0.0:
        issues.append(_issue("negative_signed_surface_radius", "hard", "Warped radius field crosses or touches the rotation axis."))

    if facets["flow_topology"] in {"radial", "mixed"} and params["exit_radius_mm"] <= params["inlet_radius_mm"]:
        issues.append(_issue("radial_or_mixed_exit_not_greater_than_inlet", "hard", "Radial/mixed meridional curve reverses radius."))

    span = _blade_span_metrics(non_mirrored_blades)
    metrics.update(span)
    if span["min_blade_span_mm"] <= max(1.0, float(params["blade_thickness_mm"]) * 1.05):
        issues.append(_issue("blade_span_collapse", "hard", "Hub-to-tip span is too small relative to blade thickness."))

    clearance = _adjacent_blade_clearance_metrics(non_mirrored_blades, params)
    metrics.update(clearance)
    if clearance["min_adjacent_centerline_gap_mm"] <= clearance["required_adjacent_gap_mm"]:
        issues.append(_issue("adjacent_blade_interference", "hard", "Adjacent blade centerline spacing is below required thickness clearance."))

    wrap = _blade_wrap_metrics(non_mirrored_blades)
    metrics.update(wrap)
    if abs(wrap["max_blade_wrap_deg"]) > 210.0:
        issues.append(_issue("excessive_blade_wrap", "hard", "Blade centerline wraps more than 210 degrees between inlet and outlet."))
    elif abs(wrap["max_blade_wrap_deg"]) > 145.0:
        issues.append(_issue("high_blade_wrap", "warning", "Blade centerline wrap is high; loft may become visually confusing."))

    if params["inlet_blade_angle_deg"] < 3.0 or params["inlet_blade_angle_deg"] > 87.0:
        issues.append(_issue("inlet_beta_silently_clamped", "warning", "Kernel clamps inlet beta to [3, 87] degrees for theta integration."))
    if params["outlet_blade_angle_deg"] < 3.0 or params["outlet_blade_angle_deg"] > 87.0:
        issues.append(_issue("outlet_beta_silently_clamped", "warning", "Kernel clamps outlet beta to [3, 87] degrees for theta integration."))

    if facets["passage_topology"] in {"single_channel", "multi_channel", "cutter"}:
        issues.append(_issue("unsupported_passage_specialization", "hard", "Facet is recorded but geometry still uses generic throughflow blades."))
    if facets["passage_topology"] == "recessed_vortex" and facets["shroud_topology"] != "open":
        issues.append(_issue("recessed_vortex_with_shroud_topology", "warning", "Current vortex/free-flow assumption expects open shroud topology."))

    if abs(float(params.get("hub_twist_deg", 0.0))) > 0.0 or abs(float(params.get("hub_warp_mm", 0.0))) > 0.0:
        issues.append(_issue("strict_revolve_hub_violation", "warning", "Hub field is warped/non-axisymmetric, not a strict NURBS surface of revolution."))

    shroud_lines = geometry["construction_lines"].get("shroud", [])
    shroud_surface = next((surface for surface in graph["surfaces"] if surface["id"] == "shroud_surface"), None)
    if shroud_surface and any(line.get("source") == "shroud_proxy" for line in shroud_lines):
        issues.append(_issue("legacy_shroud_lines_not_from_surface_graph", "warning", "Legacy shroud construction lines are not sampled from surface_graph."))

    metrics["surface_count"] = len(graph["surfaces"])
    metrics["edge_count"] = len(graph["edges"])
    metrics["blade_count_generated"] = len(blades)
    return {"issues": issues, "metrics": metrics}


def _surface_quality_metrics(graph: dict[str, Any]) -> dict[str, float]:
    min_area = math.inf
    min_normal_dot = 1.0
    max_aspect_ratio = 0.0
    for surface in graph["surfaces"]:
        grid = surface["uv_grid"]
        if len(grid) < 2 or len(grid[0]) < 2:
            continue
        normals: list[list[float | None]] = []
        for u_index in range(len(grid) - 1):
            normal_row = []
            for v_index in range(len(grid[u_index]) - 1):
                p00 = grid[u_index][v_index]
                p10 = grid[u_index + 1][v_index]
                p01 = grid[u_index][v_index + 1]
                p11 = grid[u_index + 1][v_index + 1]
                edges = [
                    _distance(p00, p10),
                    _distance(p10, p11),
                    _distance(p11, p01),
                    _distance(p01, p00),
                ]
                shortest = max(min(edges), 1e-12)
                max_aspect_ratio = max(max_aspect_ratio, max(edges) / shortest)
                normal = _cross(_vector(p00, p10), _vector(p00, p01))
                normal_len = _norm(normal)
                min_area = min(min_area, normal_len * 0.5)
                normal_row.append(_scale(normal, 1.0 / normal_len) if normal_len > 1e-12 else None)
            normals.append(normal_row)
        for u_index, row in enumerate(normals):
            for v_index, normal in enumerate(row):
                if normal is None:
                    continue
                for neighbor in (
                    normals[u_index + 1][v_index] if u_index + 1 < len(normals) else None,
                    row[v_index + 1] if v_index + 1 < len(row) else None,
                ):
                    if neighbor is not None:
                        min_normal_dot = min(min_normal_dot, _dot(normal, neighbor))
    if min_area is math.inf:
        min_area = 0.0
    return {
        "min_surface_cell_area_mm2": round(min_area, 6),
        "min_adjacent_normal_dot": round(min_normal_dot, 6),
        "max_surface_aspect_ratio": round(max_aspect_ratio, 6),
    }


def _minimum_signed_radius(geometry: dict[str, Any]) -> float:
    min_radius = math.inf
    curves = geometry["kernel"]["meridional_curves"]
    fields = geometry["kernel"]["surface_fields"]
    for key, curve_name in [("hub", "hub"), ("tip", "tip_or_shroud")]:
        warp = abs(float(fields[key].get("warp_mm", 0.0)))
        for point in curves[curve_name]:
            min_radius = min(min_radius, float(point["r_mm"]) - 0.18 * warp)
    return min_radius


def _blade_span_metrics(blades: list[dict[str, Any]]) -> dict[str, float]:
    min_span = math.inf
    for blade in blades:
        for hub, tip in zip(blade["hub_boundary"], blade["tip_boundary"]):
            min_span = min(min_span, _distance(hub, tip))
    return {"min_blade_span_mm": round(min_span if min_span is not math.inf else 0.0, 6)}


def _adjacent_blade_clearance_metrics(blades: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, float]:
    if len(blades) < 2:
        return {"min_adjacent_centerline_gap_mm": 0.0, "required_adjacent_gap_mm": float(params["blade_thickness_mm"])}
    min_gap = math.inf
    for index, blade in enumerate(blades):
        next_blade = blades[(index + 1) % len(blades)]
        for row, next_row in zip(blade["mean_surface"], next_blade["mean_surface"]):
            for point, next_point in zip(row, next_row):
                min_gap = min(min_gap, _distance(point, next_point))
    required = float(params["blade_thickness_mm"]) * 1.05
    return {
        "min_adjacent_centerline_gap_mm": round(min_gap, 6),
        "required_adjacent_gap_mm": round(required, 6),
    }


def _blade_wrap_metrics(blades: list[dict[str, Any]]) -> dict[str, float]:
    max_wrap = 0.0
    for blade in blades:
        angles = [math.atan2(point[1], point[0]) for point in blade["hub_boundary"]]
        unwrapped = [angles[0]]
        for angle in angles[1:]:
            previous = unwrapped[-1]
            while angle - previous > math.pi:
                angle -= 2.0 * math.pi
            while angle - previous < -math.pi:
                angle += 2.0 * math.pi
            unwrapped.append(angle)
        max_wrap = max(max_wrap, abs(math.degrees(unwrapped[-1] - unwrapped[0])))
    return {"max_blade_wrap_deg": round(max_wrap, 6)}


def _run_cad_subset(results: list[dict[str, Any]], out_dir: Path, cad_limit: int, timeout_sec: float) -> None:
    if cad_limit <= 0:
        return
    priority = sorted(
        range(len(results)),
        key=lambda index: (
            0 if results[index]["source"] == "preset_default" else 1,
            0 if results[index]["diagnostic_status"] == "FAIL" else 1,
            results[index]["case_id"],
        ),
    )
    selected = priority[: min(cad_limit, len(priority))]
    for index in selected:
        result = results[index]
        if result["kernel_status"] != "PASS":
            result["cad_status"] = "SKIPPED_KERNEL_FAIL"
            continue
        cad_result = _run_one_cad_case_with_timeout(result, out_dir, timeout_sec)
        result["cad_status"] = cad_result["cad_status"]
        if "cad_export" in cad_result:
            result["cad_export"] = cad_result["cad_export"]
        result["issues"].extend(cad_result.get("issues", []))


def _run_one_cad_case_with_timeout(result: dict[str, Any], out_dir: Path, timeout_sec: float) -> dict[str, Any]:
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    process = ctx.Process(target=_cad_case_worker, args=(result, str(out_dir), queue))
    process.start()
    process.join(timeout_sec)
    if process.is_alive():
        process.terminate()
        process.join(5.0)
        return {
            "cad_status": "TIMEOUT",
            "issues": [_issue("cad_export_timeout", "cad", f"CAD export exceeded {timeout_sec} seconds.")],
        }
    if process.exitcode != 0:
        return {
            "cad_status": "ERROR",
            "issues": [_issue("cad_export_process_error", "cad", f"CAD worker exited with {process.exitcode}.")],
        }
    if queue.empty():
        return {
            "cad_status": "ERROR",
            "issues": [_issue("cad_export_no_result", "cad", "CAD worker exited without returning a result.")],
        }
    return queue.get()


def _cad_case_worker(result: dict[str, Any], out_dir: str, queue: Any) -> None:
    try:
        service = RuleSynthesisService(Path(out_dir) / "cad_runs")
        engine = service.synthesize("impeller", result["preset_id"], result["facets"])
        run = service.instantiate(engine.engine_id, result["parameters"])
        exports = run.manifest["exports"]
        step_path = Path(exports["step"])
        stl_path = Path(exports["stl"])
        step_size = step_path.stat().st_size
        stl_size = stl_path.stat().st_size
        cad_result = {
            "cad_status": "PASS",
            "cad_export": {
                "run_id": run.run_id,
                "step_path": str(step_path),
                "stl_path": str(stl_path),
                "step_size_bytes": step_size,
                "stl_size_bytes": stl_size,
            },
            "issues": [],
        }
        if step_size <= 64 or stl_size <= 64:
            cad_result["cad_status"] = "FALLBACK_PLACEHOLDER"
            cad_result["issues"].append(
                _issue("cad_export_placeholder", "cad", "CADQuery failed internally; service emitted placeholder STEP/STL.")
            )
        queue.put(cad_result)
    except Exception as exc:
        queue.put({"cad_status": "ERROR", "issues": [_issue("cad_export_exception", "cad", str(exc))]})


def _summarize(results: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    issue_counts = Counter(issue["code"] for result in results for issue in result["issues"])
    hard_issue_counts = Counter(
        issue["code"] for result in results for issue in result["issues"] if issue["severity"] == "hard"
    )
    warning_issue_counts = Counter(
        issue["code"] for result in results for issue in result["issues"] if issue["severity"] == "warning"
    )
    cad_issue_counts = Counter(
        issue["code"] for result in results for issue in result["issues"] if issue["severity"] == "cad"
    )
    by_source = defaultdict(Counter)
    by_facet = defaultdict(Counter)
    for result in results:
        by_source[result["source"]][result["diagnostic_status"]] += 1
        by_facet[f"flow={result['facets']['flow_topology']}"][result["diagnostic_status"]] += 1
        by_facet[f"shroud={result['facets']['shroud_topology']}"][result["diagnostic_status"]] += 1
        by_facet[f"passage={result['facets']['passage_topology']}"][result["diagnostic_status"]] += 1

    return {
        "random_seed": RANDOM_SEED,
        "case_count": len(results),
        "random_cases_requested": args.random_cases,
        "cad_limit": args.cad_limit,
        "cad_timeout_sec": args.cad_timeout_sec,
        "kernel_status": dict(Counter(result["kernel_status"] for result in results)),
        "declared_validity_status": dict(Counter(result["declared_validity_status"] for result in results)),
        "diagnostic_status": dict(Counter(result["diagnostic_status"] for result in results)),
        "cad_status": dict(Counter(result["cad_status"] for result in results)),
        "issue_counts": dict(issue_counts.most_common()),
        "hard_issue_counts": dict(hard_issue_counts.most_common()),
        "warning_issue_counts": dict(warning_issue_counts.most_common()),
        "cad_issue_counts": dict(cad_issue_counts.most_common()),
        "by_source": {source: dict(counter) for source, counter in sorted(by_source.items())},
        "by_facet": {facet: dict(counter) for facet, counter in sorted(by_facet.items())},
        "top_hard_examples": _top_examples(results, "hard", 12),
        "top_cad_examples": _top_examples(results, "cad", 8),
    }


def _top_examples(results: list[dict[str, Any]], severity: str, limit: int) -> list[dict[str, Any]]:
    examples = []
    for result in results:
        matching = [issue for issue in result["issues"] if issue["severity"] == severity]
        if not matching:
            continue
        examples.append(
            {
                "case_id": result["case_id"],
                "source": result["source"],
                "facets": result["facets"],
                "parameters": result["parameters"],
                "issues": matching,
                "metrics": result["metrics"],
                "cad_status": result["cad_status"],
            }
        )
        if len(examples) >= limit:
            break
    return examples


def _write_outputs(out_dir: Path, results: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    (out_dir / "impeller_parameter_experiment_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "impeller_parameter_experiment_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    with (out_dir / "impeller_parameter_experiment_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "source",
                "flow_topology",
                "shroud_topology",
                "suction_topology",
                "blade_exit_geometry",
                "passage_topology",
                "kernel_status",
                "declared_validity_status",
                "diagnostic_status",
                "cad_status",
                "issue_codes",
                "min_surface_cell_area_mm2",
                "min_adjacent_normal_dot",
                "max_surface_aspect_ratio",
                "min_signed_surface_radius_mm",
                "min_blade_span_mm",
                "min_adjacent_centerline_gap_mm",
                "required_adjacent_gap_mm",
                "max_blade_wrap_deg",
            ],
        )
        writer.writeheader()
        for result in results:
            metrics = result["metrics"]
            writer.writerow(
                {
                    "case_id": result["case_id"],
                    "source": result["source"],
                    "flow_topology": result["facets"]["flow_topology"],
                    "shroud_topology": result["facets"]["shroud_topology"],
                    "suction_topology": result["facets"]["suction_topology"],
                    "blade_exit_geometry": result["facets"]["blade_exit_geometry"],
                    "passage_topology": result["facets"]["passage_topology"],
                    "kernel_status": result["kernel_status"],
                    "declared_validity_status": result["declared_validity_status"],
                    "diagnostic_status": result["diagnostic_status"],
                    "cad_status": result["cad_status"],
                    "issue_codes": ";".join(issue["code"] for issue in result["issues"]),
                    "min_surface_cell_area_mm2": metrics.get("min_surface_cell_area_mm2", ""),
                    "min_adjacent_normal_dot": metrics.get("min_adjacent_normal_dot", ""),
                    "max_surface_aspect_ratio": metrics.get("max_surface_aspect_ratio", ""),
                    "min_signed_surface_radius_mm": metrics.get("min_signed_surface_radius_mm", ""),
                    "min_blade_span_mm": metrics.get("min_blade_span_mm", ""),
                    "min_adjacent_centerline_gap_mm": metrics.get("min_adjacent_centerline_gap_mm", ""),
                    "required_adjacent_gap_mm": metrics.get("required_adjacent_gap_mm", ""),
                    "max_blade_wrap_deg": metrics.get("max_blade_wrap_deg", ""),
                }
            )


def _issue(code: str, severity: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "detail": detail}


def _distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(first, second)))


def _vector(first: list[float], second: list[float]) -> list[float]:
    return [second[index] - first[index] for index in range(3)]


def _cross(first: list[float], second: list[float]) -> list[float]:
    return [
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    ]


def _dot(first: list[float], second: list[float]) -> float:
    return sum(first[index] * second[index] for index in range(3))


def _norm(vector: list[float]) -> float:
    return math.sqrt(_dot(vector, vector))


def _scale(vector: list[float], scalar: float) -> list[float]:
    return [value * scalar for value in vector]


if __name__ == "__main__":
    main()
