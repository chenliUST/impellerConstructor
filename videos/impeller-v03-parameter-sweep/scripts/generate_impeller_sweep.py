from __future__ import annotations

import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from part_rule_synthesis.impeller_kernel import build_impeller_geometry  # noqa: E402
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset  # noqa: E402


DURATION_SECONDS = 32
GRID_U_STEP = 2
GRID_V_STEP = 2


def main() -> None:
    frames = build_frames()
    payload = {
        "schema": "impeller_v0_3_parameter_sweep_video",
        "duration_seconds": DURATION_SECONDS,
        "frame_count": len(frames),
        "source": {
            "runtime": "part_rule_synthesis v0.3",
            "kernel": "axisymmetric_throughflow_nurbs_kernel",
            "geometry_stage": "edge_closures",
        },
        "frames": frames,
    }
    data_dir = PROJECT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_path = data_dir / "impeller_sweep_data.js"
    data_path.write_text(
        "window.IMPELLER_SWEEP_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {data_path} with {len(frames)} frames")


def build_frames() -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []

    open_start = profiles(
        hub=[[120, 145], [260, 130], [470, 50], [590, 0]],
        tip=[[180, 312], [320, 306], [510, 135], [625, 92]],
    )
    open_l = profiles(
        hub=[[105, 900], [120, 850], [300, 70], [315, 0]],
        tip=[[230, 940], [245, 930], [325, 180], [340, 150]],
    )
    open_curve_start = default_curve_controls(blade_count=7, wrap=118, thickness=18)
    open_curve_end = curve_controls(
        theta=[[0, 0], [0.22, -15], [0.72, -155], [1, -220]],
        lean=[[0, 35], [0.45, -20], [1, 26]],
        leading=[[0, -0.18], [0.25, 0.06], [1, 0.22]],
        trailing=[[0, 0.20], [0.55, -0.08], [1, -0.26]],
        thickness=[[0, 22], [0.40, 15], [1, 8]],
    )

    for index in range(16):
        t = smooth(index / 15)
        profile = lerp_profiles(open_start, open_l, t)
        frames.append(
            make_frame(
                preset_id="radial_open_reference_v0_3",
                phase="Open profile sweep",
                phase_detail="Hub/tip reference curves: flat 4:1 envelope to high L-shaped envelope",
                progress=t,
                profile_overrides=profile,
                curve_overrides=open_curve_start,
                parameter_overrides={"blade_count": 7},
            )
        )

    for index, count in enumerate([7, 8, 9, 10, 11, 12, 13, 14, 15, 16]):
        t = index / 9
        frames.append(
            make_frame(
                preset_id="radial_open_reference_v0_3",
                phase="Open blade count sweep",
                phase_detail="Same profiles, increasing blade count to inspect crowding and closure behavior",
                progress=t,
                profile_overrides=open_l,
                curve_overrides=open_curve_start,
                parameter_overrides={"blade_count": count},
            )
        )

    for index in range(12):
        t = smooth(index / 11)
        frames.append(
            make_frame(
                preset_id="radial_open_reference_v0_3",
                phase="Open blade and edge curve sweep",
                phase_detail="Camber, lean, leading edge sweep, trailing edge sweep, and taper are changed together",
                progress=t,
                profile_overrides=open_l,
                curve_overrides=lerp_curves(open_curve_start, open_curve_end, t),
                parameter_overrides={"blade_count": 16, "blade_wrap_deg": lerp(118, 220, t), "blade_thickness_mm": lerp(18, 22, t)},
            )
        )

    closed_start = profiles(
        hub=[[125, 138], [270, 122], [455, 45], [570, 0]],
        tip=[[190, 305], [335, 300], [500, 130], [610, 88]],
    )
    closed_l = profiles(
        hub=[[106, 850], [120, 812], [302, 68], [318, 0]],
        tip=[[220, 905], [238, 895], [330, 182], [348, 152]],
    )
    closed_curve_start = default_curve_controls(blade_count=8, wrap=95, thickness=16)
    closed_curve_end = curve_controls(
        theta=[[0, 0], [0.30, -28], [0.72, -125], [1, -180]],
        lean=[[0, 24], [0.5, -12], [1, 18]],
        leading=[[0, -0.12], [0.5, 0.04], [1, 0.16]],
        trailing=[[0, 0.16], [0.55, -0.04], [1, -0.18]],
        thickness=[[0, 19], [0.5, 13], [1, 7]],
    )
    for index in range(16):
        t = smooth(index / 15)
        profile = lerp_profiles(closed_start, closed_l, t)
        frames.append(
            make_frame(
                preset_id="radial_closed_reference_v0_3",
                phase="Closed impeller comparison",
                phase_detail="Closed hood shell retained while profiles, blade count, and edge curves follow a similar deformation",
                progress=t,
                profile_overrides=profile,
                curve_overrides=lerp_curves(closed_curve_start, closed_curve_end, t),
                parameter_overrides={
                    "blade_count": round(6 + 8 * t),
                    "blade_wrap_deg": lerp(95, 180, t),
                    "blade_thickness_mm": lerp(16, 19, t),
                },
            )
        )

    return frames


def make_frame(
    *,
    preset_id: str,
    phase: str,
    phase_detail: str,
    progress: float,
    profile_overrides: dict[str, Any],
    curve_overrides: dict[str, Any],
    parameter_overrides: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    parameters.update(derived_profile_parameters(profile_overrides))
    parameters.update(parameter_overrides or {})
    if "mounting_bore_radius_mm" in parameters:
        parameters["mounting_bore_radius_mm"] = min(
            float(parameters["mounting_bore_radius_mm"]),
            max(2.0, float(parameters["inlet_radius_mm"]) * 0.50),
        )

    geometry = build_impeller_geometry(
        parameters,
        runtime["facets"],
        profile_overrides=profile_overrides,
        curve_overrides=curve_overrides,
        geometry_stage="edge_closures",
        display_policy=runtime.get("display_policy"),
        material_domain=runtime.get("material_domain"),
        solid_features=runtime.get("solid_features"),
    )
    graph = simplify_surface_graph(geometry["surface_graph"])
    validity = geometry["validity"]
    return {
        "phase": phase,
        "phase_detail": phase_detail,
        "progress": round(progress, 4),
        "preset_id": preset_id,
        "constructor_id": runtime["constructor_id"],
        "facets": runtime["facets"],
        "parameters": dashboard_parameters(parameters, profile_overrides, curve_overrides),
        "profile_control_points": {
            "hub": profile_overrides["hub_profile"]["control_points"],
            "tip": profile_overrides["tip_or_shroud_profile"]["control_points"],
        },
        "curve_control_points": curve_overrides,
        "validity": compact_validity(validity),
        "surface_graph": graph,
    }


def simplify_surface_graph(surface_graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "surfaces": [simplify_surface(surface) for surface in surface_graph.get("surfaces", [])],
        "named_boundary_curves": [
            {
                "id": curve.get("id"),
                "role": curve.get("role"),
                "points": decimate_points(curve.get("points", []), 2),
            }
            for curve in surface_graph.get("named_boundary_curves", [])
        ],
    }


def simplify_surface(surface: dict[str, Any]) -> dict[str, Any]:
    display = surface.get("display", {})
    return {
        "id": surface.get("id"),
        "role": surface.get("role"),
        "kind": surface.get("kind"),
        "color": display.get("color"),
        "opacity": display.get("opacity", 0.92),
        "uv_grid": decimate_grid(surface.get("uv_grid", [])),
    }


def decimate_grid(grid: list[list[list[float]]]) -> list[list[list[float]]]:
    if not grid:
        return []
    u_indices = decimated_indices(len(grid), GRID_U_STEP)
    v_indices = decimated_indices(len(grid[0]), GRID_V_STEP)
    return [
        [[round(float(grid[u][v][0]), 3), round(float(grid[u][v][1]), 3), round(float(grid[u][v][2]), 3)] for v in v_indices]
        for u in u_indices
    ]


def decimate_points(points: list[list[float]], step: int) -> list[list[float]]:
    indices = decimated_indices(len(points), step)
    return [[round(float(points[i][0]), 3), round(float(points[i][1]), 3), round(float(points[i][2]), 3)] for i in indices]


def decimated_indices(length: int, step: int) -> list[int]:
    if length <= 2:
        return list(range(length))
    indices = list(range(0, length, max(1, step)))
    if indices[-1] != length - 1:
        indices.append(length - 1)
    return indices


def compact_validity(validity: dict[str, Any]) -> dict[str, Any]:
    checks = validity.get("geometry_checks", []) + validity.get("topology_checks", []) + validity.get("engineering_checks", [])
    failures = [check["name"] for check in checks if check.get("status") not in {"PASS", "NOT_EVALUATED"}]
    return {
        "status": validity.get("status", "UNKNOWN"),
        "failures": failures,
        "geometry_check_count": len(validity.get("geometry_checks", [])),
        "topology_check_count": len(validity.get("topology_checks", [])),
    }


def dashboard_parameters(
    parameters: dict[str, Any],
    profiles_payload: dict[str, Any],
    curves_payload: dict[str, Any],
) -> dict[str, Any]:
    hub = profiles_payload["hub_profile"]["control_points"]
    tip = profiles_payload["tip_or_shroud_profile"]["control_points"]
    max_radius = max(point[0] for point in hub + tip)
    min_z = min(point[1] for point in hub + tip)
    max_z = max(point[1] for point in hub + tip)
    height = max(1.0, max_z - min_z)
    theta = curves_payload["blade_mean"]["theta_center_u_curve"]["control_points"]
    leading = curves_payload["blade_edges"]["leading_edge_sweep_v_curve"]["control_points"]
    trailing = curves_payload["blade_edges"]["trailing_edge_sweep_v_curve"]["control_points"]
    return {
        "blade_count": int(parameters["blade_count"]),
        "diameter_mm": round(max_radius * 2, 1),
        "height_mm": round(height, 1),
        "diameter_to_height": round((max_radius * 2) / height, 3),
        "inlet_radius_mm": round(float(parameters["inlet_radius_mm"]), 1),
        "exit_radius_mm": round(float(parameters["exit_radius_mm"]), 1),
        "hub_curve_height_mm": round(float(parameters["hub_curve_height_mm"]), 1),
        "inlet_blade_height_mm": round(float(parameters["inlet_blade_height_mm"]), 1),
        "outlet_blade_height_mm": round(float(parameters["outlet_blade_height_mm"]), 1),
        "blade_wrap_deg": round(abs(theta[-1][1]), 1),
        "max_lean_deg": round(max(abs(point[1]) for point in curves_payload["blade_mean"]["span_lean_u_curve"]["control_points"]), 1),
        "leading_edge_offset": round(max(abs(point[1]) for point in leading), 3),
        "trailing_edge_offset": round(max(abs(point[1]) for point in trailing), 3),
        "blade_thickness_root_mm": round(curves_payload["thickness"]["thickness_u_curve"]["control_points"][0][1], 1),
        "hub_top_tip_top_delta_mm": round(tip[0][1] - hub[0][1], 1),
        "hub_bottom_tip_bottom_delta_r_mm": round(tip[-1][0] - hub[-1][0], 1),
    }


def derived_profile_parameters(profile_payload: dict[str, Any]) -> dict[str, float]:
    hub = profile_payload["hub_profile"]["control_points"]
    tip = profile_payload["tip_or_shroud_profile"]["control_points"]
    return {
        "inlet_radius_mm": float(hub[0][0]),
        "exit_radius_mm": float(max(hub[-1][0], tip[-1][0])),
        "hub_curve_height_mm": float(max(point[1] for point in hub)),
        "inlet_blade_height_mm": float(tip[0][1] - hub[0][1]),
        "outlet_blade_height_mm": float(tip[-1][1] - hub[-1][1]),
    }


def profiles(*, hub: list[list[float]], tip: list[list[float]]) -> dict[str, Any]:
    return {
        "hub_profile": nurbs_curve(hub),
        "tip_or_shroud_profile": nurbs_curve(tip),
    }


def nurbs_curve(points: list[list[float]]) -> dict[str, Any]:
    return {
        "kind": "nurbs_curve",
        "degree": 3,
        "coordinate_system": "rz_meridional_mm",
        "control_points": [[round(float(r), 3), round(float(z), 3)] for r, z in points],
        "weights": [1.0, 1.0, 1.0, 1.0],
        "knots": [0, 0, 0, 0, 1, 1, 1, 1],
    }


def default_curve_controls(*, blade_count: int, wrap: float, thickness: float) -> dict[str, Any]:
    del blade_count
    return curve_controls(
        theta=[[0, 0], [0.33, -wrap * 0.18], [0.66, -wrap * 0.68], [1, -wrap]],
        lean=[[0, 12], [0.5, 8], [1, -8]],
        leading=[[0, -0.035], [0.5, 0], [1, 0.035]],
        trailing=[[0, 0.052], [0.5, 0], [1, -0.052]],
        thickness=[[0, thickness], [0.5, thickness * 0.78], [1, thickness * 0.55]],
    )


def curve_controls(
    *,
    theta: list[list[float]],
    lean: list[list[float]],
    leading: list[list[float]],
    trailing: list[list[float]],
    thickness: list[list[float]],
) -> dict[str, Any]:
    return {
        "blade_mean": {
            "theta_center_u_curve": {"coordinate_system": "u_theta_deg", "control_points": clean_points(theta)},
            "span_lean_u_curve": {"coordinate_system": "u_lean_deg", "control_points": clean_points(lean)},
        },
        "blade_edges": {
            "leading_edge_sweep_v_curve": {"coordinate_system": "v_support_u_offset", "control_points": clean_points(leading)},
            "trailing_edge_sweep_v_curve": {"coordinate_system": "v_support_u_offset", "control_points": clean_points(trailing)},
        },
        "thickness": {
            "thickness_u_curve": {"coordinate_system": "u_thickness_mm", "control_points": clean_points(thickness)},
        },
    }


def clean_points(points: list[list[float]]) -> list[list[float]]:
    return [[round(float(x), 3), round(float(y), 3)] for x, y in points]


def lerp_profiles(a: dict[str, Any], b: dict[str, Any], t: float) -> dict[str, Any]:
    return {
        "hub_profile": lerp_nurbs(a["hub_profile"], b["hub_profile"], t),
        "tip_or_shroud_profile": lerp_nurbs(a["tip_or_shroud_profile"], b["tip_or_shroud_profile"], t),
    }


def lerp_nurbs(a: dict[str, Any], b: dict[str, Any], t: float) -> dict[str, Any]:
    result = deepcopy(a)
    result["control_points"] = [
        [round(lerp(pa[0], pb[0], t), 3), round(lerp(pa[1], pb[1], t), 3)]
        for pa, pb in zip(a["control_points"], b["control_points"])
    ]
    return result


def lerp_curves(a: dict[str, Any], b: dict[str, Any], t: float) -> dict[str, Any]:
    result = deepcopy(a)
    for group, curves in result.items():
        for curve_id, curve in curves.items():
            curve["control_points"] = [
                [round(lerp(pa[0], pb[0], t), 3), round(lerp(pa[1], pb[1], t), 3)]
                for pa, pb in zip(a[group][curve_id]["control_points"], b[group][curve_id]["control_points"])
            ]
    return result


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smooth(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * t)


if __name__ == "__main__":
    main()
