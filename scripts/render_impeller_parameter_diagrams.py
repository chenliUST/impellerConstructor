from __future__ import annotations

import math
from html import escape
from pathlib import Path
from typing import Any, Callable, Iterable

from part_rule_synthesis.impeller_kernels.axisymmetric_throughflow_nurbs import (
    build_axisymmetric_throughflow_nurbs_geometry,
)
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


WIDTH = 1120
HEIGHT = 760


def render_all_diagrams(output_dir: Path | str | None = None) -> list[Path]:
    root = Path(output_dir) if output_dir is not None else Path("docs") / "impeller_parameter_diagrams"
    root.mkdir(parents=True, exist_ok=True)

    open_runtime, open_params, open_facets, open_geometry = _preset_geometry("radial_open_reference")
    closed_runtime, closed_params, closed_facets, closed_geometry = _preset_geometry("radial_closed_reference")

    outputs = [
        root / "01_meridional_parameters.svg",
        root / "02_blade_uv_boundaries.svg",
        root / "03_blade_thickness_and_lean.svg",
        root / "04_open_closed_tip_support.svg",
        root / "impeller_parameter_geometry.md",
    ]
    outputs[0].write_text(_render_meridional(open_params, open_geometry), encoding="utf-8")
    outputs[1].write_text(_render_blade_uv(open_params, open_geometry), encoding="utf-8")
    outputs[2].write_text(_render_thickness_and_lean(open_params, open_geometry), encoding="utf-8")
    outputs[3].write_text(
        _render_open_closed(open_params, open_geometry, closed_params, closed_geometry),
        encoding="utf-8",
    )
    outputs[4].write_text(
        _render_markdown(root, open_runtime, open_params, open_facets, closed_runtime, closed_params, closed_facets),
        encoding="utf-8",
    )
    return outputs


def _preset_geometry(preset_id: str) -> tuple[dict[str, Any], dict[str, float], dict[str, str], dict[str, Any]]:
    runtime = compile_impeller_runtime_preset(preset_id)
    params = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    facets = runtime["facets"]
    geometry = build_axisymmetric_throughflow_nurbs_geometry(params, facets, runtime["shape_control"])
    return runtime, params, facets, geometry


def _render_meridional(params: dict[str, float], geometry: dict[str, Any]) -> str:
    hub_profile = geometry["kernel"]["meridional_profiles"]["hub"]
    tip_profile = geometry["kernel"]["meridional_profiles"]["tip_or_shroud"]
    hub_curve = geometry["kernel"]["meridional_curves"]["hub"]
    tip_curve = geometry["kernel"]["meridional_curves"]["tip_or_shroud"]
    hub_points = [(point["r_mm"], point["z_mm"]) for point in hub_curve]
    tip_points = [(point["r_mm"], point["z_mm"]) for point in tip_curve]
    hub_cp = [(point[0], point[1]) for point in hub_profile["control_points"]]
    tip_cp = [(point[0], point[1]) for point in tip_profile["control_points"]]
    mapper = _rz_mapper(hub_points + tip_points + hub_cp + tip_cp, WIDTH, HEIGHT, 90, 155, 150, 130)
    body: list[str] = []

    body.append(_text(50, 48, "Meridional support parameters", "title"))
    body.append(_text(50, 76, "Generated from axisymmetric_throughflow_nurbs: hub/tip NURBS profiles sampled by the current kernel.", "small"))
    body.extend(_axes(mapper, "R radius (mm)", "Z height (mm)"))
    body.append(_polyline(mapper, hub_cp, "#64748b", 1.6, dash="6 5"))
    body.append(_polyline(mapper, tip_cp, "#64748b", 1.6, dash="6 5"))
    body.append(_polyline(mapper, hub_points, "#2f7d67", 4.0))
    body.append(_polyline(mapper, tip_points, "#2f6f9e", 4.0))
    for index, point in enumerate(hub_cp):
        body.append(_circle(*mapper(point), 5, "#2f7d67"))
        body.append(_text(mapper(point)[0] + 8, mapper(point)[1] - 6, f"H{index}", "small"))
    for index, point in enumerate(tip_cp):
        body.append(_circle(*mapper(point), 5, "#2f6f9e"))
        body.append(_text(mapper(point)[0] + 8, mapper(point)[1] - 6, f"T{index}", "small"))

    hub0, hub1 = hub_points[0], hub_points[-1]
    tip0, tip1 = tip_points[0], tip_points[-1]
    hub_top = max(hub_points, key=lambda point: point[1])
    z0 = 0.0

    _dim_h(body, mapper, (0.0, tip0[1] + 24.0), (tip0[0], tip0[1] + 24.0), f"inlet_radius_mm = {params['inlet_radius_mm']:.0f}")
    _dim_h(body, mapper, (0.0, tip1[1] + 30.0), (tip1[0], tip1[1] + 30.0), f"exit_radius_mm = {params['exit_radius_mm']:.0f}")
    _dim_v(body, mapper, hub0, tip0, f"inlet_blade_height_mm = {params['inlet_blade_height_mm']:.0f}")
    _dim_v(body, mapper, hub1, tip1, f"outlet_blade_height_mm = {params['outlet_blade_height_mm']:.0f}")
    _dim_v(body, mapper, (params["mounting_bore_radius_mm"] * 1.18, z0), (params["mounting_bore_radius_mm"] * 1.18, hub_top[1]), f"hub_curve_height_mm = {params['hub_curve_height_mm']:.0f}")
    _dim_h(body, mapper, (0.0, 14.0), (params["mounting_bore_radius_mm"], 14.0), f"mounting_bore_radius_mm = {params['mounting_bore_radius_mm']:.0f}")

    body.append(_legend(780, 120, [("Hub NURBS profile", "#2f7d67"), ("Tip/shroud support profile", "#2f6f9e"), ("Control polygon", "#64748b")]))
    body.append(_note_box(710, 275, 340, 188, [
        "Current formula:",
        "hub_profile = clamped cubic NURBS in R-Z",
        "tip_profile = clamped cubic NURBS in R-Z",
        "surface = revolve(profile, Z axis)",
        "",
        "Not wired in this kernel yet:",
        "hub_base_radius_mm",
        "hub_nose_radius_mm",
        "hub_profile_convexity",
    ]))
    return _svg(WIDTH, HEIGHT, body)


def _render_blade_uv(params: dict[str, float], geometry: dict[str, Any]) -> str:
    blade = geometry["sampled_blades"][0]
    mean = blade["mean_surface"]
    points = [point for row in mean for point in row]
    mapper = _xy_mapper(points, WIDTH, HEIGHT, 90, 130, 90, 120)
    body: list[str] = []
    body.append(_text(50, 48, "Blade UV boundaries and planform", "title"))
    body.append(_text(50, 76, "Generated from sampled blade mean_surface, not from STL triangle edges.", "small"))

    for row_index, row in enumerate(mean):
        if row_index % 4 == 0:
            body.append(_polyline(mapper, [(p[0], p[1]) for p in row], "#8aa5a0", 1.0, dash="3 4"))
    for v_index in range(0, len(mean[0]), 2):
        body.append(_polyline(mapper, [(row[v_index][0], row[v_index][1]) for row in mean], "#517b89", 1.0, dash="3 4"))

    boundary_specs = [
        ("blade_root_boundary: v=0", blade["blade_root_boundary"], "#22a06b"),
        ("blade_tip_boundary: v=1", blade["blade_tip_boundary"], "#2586b8"),
        ("leading_edge_boundary: u=0", blade["leading_edge_boundary"], "#d9821f"),
        ("trailing_edge_boundary: u=1", blade["trailing_edge_boundary"], "#d64545"),
    ]
    for label, boundary, color in boundary_specs:
        body.append(_polyline(mapper, [(p[0], p[1]) for p in boundary], color, 4.0))
        anchor = boundary[len(boundary) // 2]
        px, py = mapper((anchor[0], anchor[1]))
        body.append(_text(px + 10, py - 8, label, "label"))

    mid_v = len(mean[0]) // 2
    mid_u = len(mean) // 2
    leading_mid = mean[0][mid_v]
    trailing_mid = mean[-1][mid_v]
    root_mid = mean[mid_u][0]
    tip_mid = mean[mid_u][-1]
    _arrow(body, mapper((leading_mid[0], leading_mid[1])), mapper((trailing_mid[0], trailing_mid[1])), "#111827")
    _arrow(body, mapper((root_mid[0], root_mid[1])), mapper((tip_mid[0], tip_mid[1])), "#111827")
    body.append(_text(*_midpoint(mapper((leading_mid[0], leading_mid[1])), mapper((trailing_mid[0], trailing_mid[1]))), "u increases: leading -> trailing", "label"))
    span_mid = _midpoint(mapper((root_mid[0], root_mid[1])), mapper((tip_mid[0], tip_mid[1])))
    body.append(_text(span_mid[0] + 10, span_mid[1] + 18, "v increases: hub/root -> tip", "label"))

    body.append(_note_box(740, 118, 330, 250, [
        f"blade_count = {int(params['blade_count'])}",
        "copies this blade around Z.",
        "",
        f"blade_wrap_deg = {params['blade_wrap_deg']:.0f}",
        "drives theta(u) from leading to trailing.",
        "",
        f"leading_edge_sweep_mm = {params['leading_edge_sweep_mm']:.0f}",
        f"trailing_edge_sweep_mm = {params['trailing_edge_sweep_mm']:.0f}",
        "shift support_u across span at u=0/u=1.",
    ]))
    body.append(_note_box(740, 410, 330, 145, [
        "Theta field used now:",
        "theta = base + wrap*smoothstep(u)",
        "      + (lean*sin(pi*u) + edge_lean)",
        "        * (v - 0.5)",
    ]))
    return _svg(WIDTH, HEIGHT, body)


def _render_thickness_and_lean(params: dict[str, float], geometry: dict[str, Any]) -> str:
    blade = geometry["sampled_blades"][0]
    body: list[str] = []
    body.append(_text(50, 48, "Blade thickness, pressure/suction offset, and lean", "title"))
    body.append(_text(50, 76, "Generated from pressure_surface, suction_surface, and mean_surface samples.", "small"))
    _draw_thickness_section(body, blade, 0, 230, 138, "u=0 leading edge")
    _draw_thickness_section(body, blade, len(blade["mean_surface"]) // 2, 530, 138, "u=0.5 mid blade")
    _draw_thickness_section(body, blade, len(blade["mean_surface"]) - 1, 830, 138, "u=1 trailing edge")
    body.append(_note_box(70, 560, 470, 132, [
        f"blade_thickness_mm = {params['blade_thickness_mm']:.1f}",
        "Pressure and suction are angular offsets around the mean surface.",
        "The kernel tapers thickness along u:",
        "thickness(u) = blade_thickness_mm * (1 - 0.45*smoothstep(u))",
    ]))
    body.append(_note_box(590, 560, 460, 132, [
        f"blade_lean_deg = {params['blade_lean_deg']:.1f}",
        f"leading_edge_lean_deg = {params['leading_edge_lean_deg']:.1f}",
        f"trailing_edge_lean_deg = {params['trailing_edge_lean_deg']:.1f}",
        "These change theta as a spanwise angular term multiplied by (v - 0.5).",
    ]))
    return _svg(WIDTH, HEIGHT, body)


def _render_open_closed(
    open_params: dict[str, float],
    open_geometry: dict[str, Any],
    closed_params: dict[str, float],
    closed_geometry: dict[str, Any],
) -> str:
    body: list[str] = []
    body.append(_text(50, 48, "Open vs closed tip support surface", "title"))
    body.append(_text(50, 76, "The same blade_tip_support_surface concept is reference-only in open impellers and material in closed impellers.", "small"))
    _draw_support_pair(body, open_geometry, 70, 128, 450, 480, "Open: tip support is reference-only", dashed_tip=True)
    _draw_support_pair(body, closed_geometry, 610, 128, 450, 480, "Closed: tip support is front shroud material", dashed_tip=False)
    body.append(_note_box(110, 640, 900, 70, [
        "shroud_topology changes material semantics of the tip support. It does not change the blade v=1 boundary definition:",
        "blade_tip_boundary still conforms to blade_tip_support_surface for both open and closed cases.",
    ]))
    return _svg(WIDTH, HEIGHT, body)


def _render_markdown(
    output_dir: Path,
    open_runtime: dict[str, Any],
    open_params: dict[str, float],
    open_facets: dict[str, str],
    closed_runtime: dict[str, Any],
    closed_params: dict[str, float],
    closed_facets: dict[str, str],
) -> str:
    return "\n".join(
        [
            "# Impeller Parameter Geometry",
            "",
            "These figures are generated by `scripts/render_impeller_parameter_diagrams.py` from the current `axisymmetric_throughflow_nurbs` kernel. They are not AI-generated images.",
            "",
            "## Figures",
            "",
            "![Meridional parameters](01_meridional_parameters.svg)",
            "",
            "![Blade UV boundaries](02_blade_uv_boundaries.svg)",
            "",
            "![Blade thickness and lean](03_blade_thickness_and_lean.svg)",
            "",
            "![Open and closed tip support](04_open_closed_tip_support.svg)",
            "",
            "## Currently active kernel parameters",
            "",
            "| Parameter | Geometric meaning in the current kernel |",
            "| --- | --- |",
            "| `blade_count` | Patterns the sampled blade around the Z axis. |",
            "| `inlet_radius_mm` | Tip/support radius at `u=0`; also contributes to hub NURBS control points. |",
            "| `exit_radius_mm` | Tip/support radius at `u=1`; also defines radial span and hub bottom radius. |",
            "| `inlet_blade_height_mm` | Z separation between hub and tip support near the inlet/leading side. |",
            "| `outlet_blade_height_mm` | Z separation between hub and tip support near the outlet/trailing side. |",
            "| `hub_curve_height_mm` | Target height for the top of the hub meridional profile, subject to kernel safety clamps. |",
            "| `mounting_bore_radius_mm` | Radius of the mounting bore cylinder, clamped against the hub profile. |",
            "| `blade_wrap_deg` | Main angular progression term in `theta(u,v)` along blade `u`. |",
            "| `blade_lean_deg` | Mid-blade spanwise angular lean term in `theta(u,v)`. |",
            "| `leading_edge_lean_deg` | Spanwise angular lean term at `u=0`. |",
            "| `trailing_edge_lean_deg` | Spanwise angular lean term at `u=1`. |",
            "| `leading_edge_sweep_mm` | Support-curve `u` shift across span near the leading edge. |",
            "| `trailing_edge_sweep_mm` | Support-curve `u` shift across span near the trailing edge. |",
            "| `blade_thickness_mm` | Pressure/suction angular offset around the mean surface; tapered along `u`. |",
            "",
            "## Currently not wired into this kernel",
            "",
            "| Parameter | Current status |",
            "| --- | --- |",
            "| `hub_base_radius_mm` | Exposed as a shape-control semantic handle in the frontend, but not used by `axisymmetric_throughflow_nurbs` yet. |",
            "| `hub_nose_radius_mm` | Exposed as a shape-control semantic handle in the frontend, but not used by `axisymmetric_throughflow_nurbs` yet. |",
            "| `hub_profile_convexity` | Exposed as a shape-control semantic handle in the frontend, but not used by `axisymmetric_throughflow_nurbs` yet. |",
            "| `root_fillet_radius_mm` | Present in DSL shape-control/validity vocabulary, but the current kernel creates ruled edge closure surfaces rather than radius-driven fillets. |",
            "| `inlet_blade_angle_deg` / `outlet_blade_angle_deg` | Preserved in DSL presets and legacy paths, but the current axisymmetric NURBS kernel uses `blade_wrap_deg` and lean/sweep fields instead. |",
            "",
            "## Preset context",
            "",
            f"- Open preset: `{open_runtime['preset_id']}` with facets `{open_facets}` and {len(open_params)} parameters.",
            f"- Closed preset: `{closed_runtime['preset_id']}` with facets `{closed_facets}` and {len(closed_params)} parameters.",
            f"- Output directory: `{output_dir}`.",
            "",
        ]
    )


def _draw_support_pair(
    body: list[str],
    geometry: dict[str, Any],
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    dashed_tip: bool,
) -> None:
    hub = [(point["r_mm"], point["z_mm"]) for point in geometry["kernel"]["meridional_curves"]["hub"]]
    tip = [(point["r_mm"], point["z_mm"]) for point in geometry["kernel"]["meridional_curves"]["tip_or_shroud"]]
    mapper = _rz_mapper(hub + tip, width, height, x + 25, y + 45, 35, 55)
    body.append(_rect(x, y, width, height, "#ffffff", "#d8e0dc"))
    body.append(_text(x + 20, y + 28, title, "subtitle"))
    body.extend(_axes(mapper, "R", "Z"))
    body.append(_polyline(mapper, hub, "#2f7d67", 3.6))
    body.append(_polyline(mapper, tip, "#2f6f9e", 3.6, dash="9 6" if dashed_tip else ""))
    if not dashed_tip:
        filled = tip + list(reversed(hub))
        body.append(_polygon(mapper, filled, "#9db7c5", 0.22, "#9db7c5"))
    body.append(_text(x + 28, y + height - 18, "blade v=0 conforms to hub; blade v=1 conforms to tip support", "small"))


def _draw_thickness_section(body: list[str], blade: dict[str, Any], u_index: int, cx: float, top: float, title: str) -> None:
    pressure = blade["pressure_surface"][u_index]
    suction = blade["suction_surface"][u_index]
    mean = blade["mean_surface"][u_index]
    y0 = top + 46
    y1 = top + 360
    scale = 8.0
    center_x = cx
    body.append(_rect(cx - 135, top, 270, 410, "#ffffff", "#d8e0dc"))
    body.append(_text(cx - 105, top + 28, title, "subtitle"))
    body.append(_line(cx, y0, cx, y1, "#64748b", 1.0, dash="5 4"))
    pressure_line = []
    suction_line = []
    mean_line = []
    for v_index, mean_point in enumerate(mean):
        v = v_index / (len(mean) - 1)
        theta = math.atan2(mean_point[1], mean_point[0])
        tangent = (-math.sin(theta), math.cos(theta), 0.0)
        p_offset = _dot(_sub(pressure[v_index], mean_point), tangent)
        s_offset = _dot(_sub(suction[v_index], mean_point), tangent)
        y = y1 - v * (y1 - y0)
        pressure_line.append((center_x + p_offset * scale, y))
        suction_line.append((center_x + s_offset * scale, y))
        mean_line.append((center_x, y))
    body.append(_polyline_pixels(pressure_line, "#2f7d67", 3.0))
    body.append(_polyline_pixels(suction_line, "#2f6f9e", 3.0))
    body.append(_polyline_pixels(mean_line, "#111827", 1.6, dash="4 4"))
    mid = len(mean) // 2
    py = pressure_line[mid][1]
    _arrow(body, suction_line[mid], pressure_line[mid], "#d64545")
    body.append(_text(min(suction_line[mid][0], pressure_line[mid][0]) - 35, py - 12, "local thickness", "small"))
    body.append(_text(cx + 52, y0 + 5, "v=1 tip", "small"))
    body.append(_text(cx + 52, y1, "v=0 hub", "small"))


def _rz_mapper(
    points: list[tuple[float, float]],
    width: float,
    height: float,
    left: float,
    top: float,
    right: float,
    bottom: float,
) -> Callable[[tuple[float, float]], tuple[float, float]]:
    r_values = [0.0] + [point[0] for point in points]
    z_values = [0.0] + [point[1] for point in points]
    r_min, r_max = min(r_values), max(r_values)
    z_min, z_max = min(z_values), max(z_values)
    r_pad = max((r_max - r_min) * 0.08, 1.0)
    z_pad = max((z_max - z_min) * 0.12, 1.0)
    r_min, r_max = r_min, r_max + r_pad
    z_min, z_max = z_min, z_max + z_pad
    plot_w = width - left - right
    plot_h = height - top - bottom

    def map_point(point: tuple[float, float]) -> tuple[float, float]:
        r, z = point
        px = left + (r - r_min) / max(r_max - r_min, 1.0) * plot_w
        py = top + plot_h - (z - z_min) / max(z_max - z_min, 1.0) * plot_h
        return px, py

    map_point.bounds = (r_min, r_max, z_min, z_max, left, top, plot_w, plot_h)  # type: ignore[attr-defined]
    return map_point


def _xy_mapper(
    points: list[list[float]],
    width: float,
    height: float,
    left: float,
    top: float,
    right: float,
    bottom: float,
) -> Callable[[tuple[float, float]], tuple[float, float]]:
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    span = max(x_max - x_min, y_max - y_min, 1.0)
    x_mid = (x_min + x_max) / 2
    y_mid = (y_min + y_max) / 2
    x_min, x_max = x_mid - span / 2, x_mid + span / 2
    y_min, y_max = y_mid - span / 2, y_mid + span / 2
    plot_w = width - left - right
    plot_h = height - top - bottom

    def map_point(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        px = left + (x - x_min) / span * plot_w
        py = top + plot_h - (y - y_min) / span * plot_h
        return px, py

    return map_point


def _axes(mapper: Callable[[tuple[float, float]], tuple[float, float]], x_label: str, y_label: str) -> list[str]:
    r_min, r_max, z_min, z_max, left, top, plot_w, plot_h = mapper.bounds  # type: ignore[attr-defined]
    return [
        _line(left, top + plot_h, left + plot_w, top + plot_h, "#94a3b8", 1.0),
        _line(left, top, left, top + plot_h, "#94a3b8", 1.0),
        _text(left + plot_w - 95, top + plot_h + 34, x_label, "small"),
        _text(left - 55, top + 14, y_label, "small"),
    ]


def _dim_h(body: list[str], mapper: Callable[[tuple[float, float]], tuple[float, float]], start: tuple[float, float], end: tuple[float, float], label: str) -> None:
    p1, p2 = mapper(start), mapper(end)
    _arrow(body, p1, p2, "#111827")
    body.append(_line(p1[0], p1[1] - 8, p1[0], p1[1] + 8, "#111827", 1.0))
    body.append(_line(p2[0], p2[1] - 8, p2[0], p2[1] + 8, "#111827", 1.0))
    body.append(_text((p1[0] + p2[0]) / 2 - 55, p1[1] - 10, label, "label"))


def _dim_v(body: list[str], mapper: Callable[[tuple[float, float]], tuple[float, float]], start: tuple[float, float], end: tuple[float, float], label: str) -> None:
    p1, p2 = mapper(start), mapper(end)
    x = max(p1[0], p2[0]) + 18
    _arrow(body, (x, p1[1]), (x, p2[1]), "#111827")
    body.append(_line(p1[0], p1[1], x + 8, p1[1], "#111827", 1.0, dash="3 4"))
    body.append(_line(p2[0], p2[1], x + 8, p2[1], "#111827", 1.0, dash="3 4"))
    text_x = x + 10 if x < WIDTH - 260 else x - 230
    body.append(_text(text_x, (p1[1] + p2[1]) / 2, label, "label"))


def _svg(width: int, height: int, body: list[str]) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            "<defs>",
            '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">',
            '<path d="M0,0 L0,6 L9,3 z" fill="context-stroke" />',
            "</marker>",
            "<style>",
            ".title{font:700 26px Arial,sans-serif;fill:#17231f}",
            ".subtitle{font:700 16px Arial,sans-serif;fill:#24342f}",
            ".label{font:700 13px Arial,sans-serif;fill:#17231f}",
            ".small{font:12px Arial,sans-serif;fill:#40514b}",
            "</style>",
            "</defs>",
            '<rect x="0" y="0" width="100%" height="100%" fill="#f5f7f6"/>',
            *body,
            "</svg>",
        ]
    )


def _polyline(mapper: Callable[[tuple[float, float]], tuple[float, float]], points: Iterable[tuple[float, float]], color: str, width: float, dash: str = "") -> str:
    mapped = " ".join(f"{x:.2f},{y:.2f}" for x, y in (mapper(point) for point in points))
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<polyline points="{mapped}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>'


def _polyline_pixels(points: Iterable[tuple[float, float]], color: str, width: float, dash: str = "") -> str:
    mapped = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<polyline points="{mapped}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>'


def _polygon(mapper: Callable[[tuple[float, float]], tuple[float, float]], points: Iterable[tuple[float, float]], color: str, opacity: float, stroke: str) -> str:
    mapped = " ".join(f"{x:.2f},{y:.2f}" for x, y in (mapper(point) for point in points))
    return f'<polygon points="{mapped}" fill="{color}" fill-opacity="{opacity}" stroke="{stroke}" stroke-width="1.0"/>'


def _line(x1: float, y1: float, x2: float, y2: float, color: str, width: float, dash: str = "") -> str:
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="{width}" stroke-linecap="round"{dash_attr}/>'


def _arrow(body: list[str], p1: tuple[float, float], p2: tuple[float, float], color: str) -> None:
    body.append(f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" stroke="{color}" stroke-width="2" stroke-linecap="round" marker-end="url(#arrow)"/>')


def _circle(x: float, y: float, r: float, color: str) -> str:
    return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{color}"/>'


def _rect(x: float, y: float, width: float, height: float, fill: str, stroke: str) -> str:
    return f'<rect x="{x:.2f}" y="{y:.2f}" width="{width:.2f}" height="{height:.2f}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'


def _text(x: float, y: float, value: str, class_name: str) -> str:
    return f'<text x="{x:.2f}" y="{y:.2f}" class="{class_name}">{escape(value)}</text>'


def _legend(x: float, y: float, items: list[tuple[str, str]]) -> str:
    parts = [_rect(x, y, 260, 28 + len(items) * 26, "#ffffff", "#d8e0dc")]
    for index, (label, color) in enumerate(items):
        yy = y + 30 + index * 26
        parts.append(_line(x + 18, yy - 5, x + 52, yy - 5, color, 4.0))
        parts.append(_text(x + 62, yy, label, "small"))
    return "\n".join(parts)


def _note_box(x: float, y: float, width: float, height: float, lines: list[str]) -> str:
    parts = [_rect(x, y, width, height, "#ffffff", "#d8e0dc")]
    for index, line in enumerate(lines):
        cls = "label" if index == 0 else "small"
        parts.append(_text(x + 16, y + 26 + index * 18, line, cls))
    return "\n".join(parts)


def _midpoint(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float, float]:
    return (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2


def _sub(a: list[float], b: list[float]) -> tuple[float, float, float]:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


if __name__ == "__main__":
    for generated in render_all_diagrams():
        print(generated)
