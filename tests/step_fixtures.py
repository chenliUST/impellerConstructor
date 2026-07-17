from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence


def write_periodic_impeller_step(path: Path, *, blade_count: int = 8) -> Path:
    import cadquery as cq

    hub = cq.Workplane("XY").circle(12.0).circle(4.0).extrude(5.0).val()
    blade = cq.Workplane("XY").box(20.0, 2.4, 8.0).translate((17.0, 0.0, 4.0)).val()
    shape = hub
    for index in range(blade_count):
        shape = shape.fuse(
            blade.rotate((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 360.0 * index / blade_count)
        )
    cq.exporters.export(shape, str(path), exportType="STEP")
    return path


def write_axis_first_impeller_step(
    path: Path,
    *,
    blade_count: int = 8,
    splitter_count: int = 0,
    splitter_phase_fraction: float = 0.37,
    closed_shroud: bool = False,
    large_nonperiodic_decoy: bool = False,
    auxiliary_holes: bool = False,
    repeated_connected_auxiliary_holes: bool = False,
    root_blend_radius_mm: float = 0.0,
    rotation_axis: Sequence[float] = (0.0, 1.0, 0.0),
    rotation_deg: float = 0.0,
    translation_mm: Sequence[float] = (0.0, 0.0, 0.0),
) -> Path:
    import cadquery as cq

    hub_outer_radius = 32.0
    hub_top_z = 0.8
    hub = (
        cq.Workplane("XY")
        .circle(hub_outer_radius)
        .circle(4.0)
        .extrude(hub_top_z)
    )
    if auxiliary_holes:
        for angle_deg in (17.0, 143.0, 251.0):
            angle_rad = math.radians(angle_deg)
            center = (8.2 * math.cos(angle_rad), 8.2 * math.sin(angle_rad))
            cutter = (
                cq.Workplane("XY")
                .center(*center)
                .circle(0.7)
                .extrude(hub_top_z)
            )
            hub = hub.cut(cutter)
    if repeated_connected_auxiliary_holes:
        for index in range(blade_count):
            angle_rad = 2.0 * math.pi * index / blade_count
            center = (8.2 * math.cos(angle_rad), 8.2 * math.sin(angle_rad))
            through_hole = (
                cq.Workplane("XY")
                .center(*center)
                .circle(0.62)
                .extrude(hub_top_z)
            )
            counterbore = (
                cq.Workplane("XY")
                .workplane(offset=0.48)
                .center(*center)
                .circle(1.05)
                .extrude(hub_top_z - 0.48)
            )
            hub = hub.cut(through_hole).cut(counterbore)
    shape = hub.val()

    main_blade = _variable_thickness_blade(
        cq,
        root_radius=11.4,
        tip_radius=31.0,
        height=7.2,
        z_offset=0.6,
    )
    shape = _pattern_fuse(shape, main_blade, blade_count, phase_deg=0.0)

    if splitter_count:
        splitter = _variable_thickness_blade(
            cq,
            root_radius=18.5,
            tip_radius=30.0,
            root_half_width=0.9,
            tip_half_width=0.45,
            height=7.4,
            z_offset=0.4,
        )
        phase_deg = splitter_phase_fraction * (360.0 / blade_count)
        shape = _pattern_fuse(shape, splitter, splitter_count, phase_deg=phase_deg)

    if root_blend_radius_mm > 0.0:
        shape = _fillet_blade_hub_attachment_edges(
            shape,
            radius_mm=root_blend_radius_mm,
            hub_top_z=hub_top_z,
        )

    if closed_shroud:
        shroud = (
            cq.Workplane("XY")
            .workplane(offset=7.4)
            .circle(31.5)
            .circle(10.0)
            .extrude(0.6)
            .val()
        )
        shape = shape.fuse(shroud)
    if large_nonperiodic_decoy:
        decoy = (
            cq.Workplane("XY")
            .workplane(offset=-0.8)
            .circle(25.0)
            .circle(11.5)
            .extrude(1.2)
            .val()
        )
        shape = shape.fuse(decoy)

    if abs(float(rotation_deg)) > 1.0e-12:
        axis = tuple(float(value) for value in rotation_axis)
        shape = shape.rotate((0.0, 0.0, 0.0), axis, float(rotation_deg))
    translation = tuple(float(value) for value in translation_mm)
    if any(abs(value) > 1.0e-12 for value in translation):
        shape = shape.translate(translation)

    cq.exporters.export(shape, str(path), exportType="STEP")
    return path


def write_axis_first_representable_step(
    path: Path, *, blade_count: int = 8
) -> Path:
    """Write a single-solid source that is representable by V1.1.2.

    The blade body is lofted from the public V1.1.2 five-loop family.  A
    separate, wider root loft intersects the hub and leaves an authenticated
    retained-root boundary.  This fixture therefore exercises the mapper with
    the real thickness field and rounded edge-cap mathematics instead of a
    constant-thickness rectangular proxy.
    """
    import cadquery as cq
    from part_rule_synthesis.impeller_v11_2_canonical import (
        canonical_nurbs_from_v11_defaults,
    )
    from part_rule_synthesis.impeller_v11_blade_to_blade_loop import (
        build_v11_blade_to_blade_loop_family,
    )

    hub_height = 34.0
    hub_inlet_radius = 10.0
    hub_exit_radius = 12.0
    tip_inlet_radius = 20.0
    tip_exit_radius = 22.0
    root_lift = 1.0
    outer_hub = cq.Solid.makeCone(
        hub_inlet_radius, hub_exit_radius, hub_height
    )
    bore = cq.Solid.makeCylinder(4.0, hub_height)
    cavity_bottom = 4.0
    cavity_height = 26.0
    cavity_outer = cq.Solid.makeCone(
        8.7,
        10.2,
        cavity_height,
        cq.Vector(0.0, 0.0, cavity_bottom),
    )
    retained_core = cq.Solid.makeCylinder(
        7.0,
        cavity_height,
        cq.Vector(0.0, 0.0, cavity_bottom),
    )
    annular_cavity = cavity_outer.cut(retained_core)
    shape = outer_hub.cut(bore).cut(annular_cavity)

    profile_z = [0.0, 6.8, 13.6, 20.4, 27.2, hub_height]
    parameters = {
        "blade_count": int(blade_count),
        "blade_thickness_mm": 3.0,
        "inlet_radius_mm": hub_inlet_radius,
        "exit_radius_mm": hub_exit_radius,
        "inlet_blade_height_mm": tip_inlet_radius - hub_inlet_radius,
        "outlet_blade_height_mm": tip_exit_radius - hub_exit_radius,
        "blade_wrap_deg": 0.0,
        "blade_lean_deg": 0.0,
        "leading_edge_lean_deg": 0.0,
        "trailing_edge_lean_deg": 0.0,
        "leading_edge_sweep_mm": 0.0,
        "trailing_edge_sweep_mm": 0.0,
    }
    defaults = {
        "span_stations_h": [0.0, 0.25, 0.5, 0.75, 1.0],
        "main_blade_count": int(blade_count),
        "splitter_blade_count": 0,
        "main_streamwise_interval_s": [0.05, 0.95],
        "splitter_streamwise_interval_s": [0.35, 0.88],
        "splitter_phase_offset_pitch": 0.5,
        "average_blade_thickness_mm": 3.0,
        "maximum_blade_thickness_mm": 3.0,
        "main_flow_turn_q_mm": 1.0e-6,
        "spanwise_flow_turn_delta_q_mm": 0.0,
        "midspan_bow_q_mm": 0.0,
        "root_attachment_width_mm": root_lift,
        "root_attachment_lift_mm": root_lift,
        "root_blade_lift_mm": root_lift,
        "tip_attachment_mode": "open_tip_dome",
        "hub_profile_rz_mm": [
            [hub_inlet_radius + (hub_exit_radius - hub_inlet_radius) * z / hub_height, z]
            for z in profile_z
        ],
        "tip_or_shroud_profile_rz_mm": [
            [tip_inlet_radius + (tip_exit_radius - tip_inlet_radius) * z / hub_height, z]
            for z in profile_z
        ],
        "enforce_support_profile_contract": False,
        "blade_hub_angle_contract_deg": [0.0, 180.0],
        "minimum_active_blade_height_mm": 1.0,
    }
    defaults["canonical_nurbs_parameterization"] = (
        canonical_nurbs_from_v11_defaults(
            parameters, defaults, source="v116_representable_step_fixture"
        )
    )
    loop_family = build_v11_blade_to_blade_loop_family(parameters, defaults)
    representative = next(
        blade
        for blade in loop_family["blades"]
        if blade["blade_class"] == "main" and blade["blade_pair_index"] == 0
    )

    def section_wire(
        loop, active_span_fraction: float, *, q_scale: float = 1.0
    ):
        edges = []
        for segment_name, reverse in (
            ("leading_edge", False),
            ("suction_side", False),
            ("trailing_edge", False),
            ("pressure_side", True),
        ):
            points = list(loop["segments"][segment_name]["points_s_q"])
            if reverse:
                points.reverse()
            edges.append(
                cq.Edge.makeSpline(
                    [
                        cq.Vector(
                            hub_inlet_radius
                            + (hub_exit_radius - hub_inlet_radius) * s
                            + root_lift
                            + (tip_inlet_radius - hub_inlet_radius - root_lift)
                            * active_span_fraction,
                            q_scale * q_mm,
                            hub_height * s,
                        )
                        for s, q_mm in points
                    ]
                )
            )
        return cq.Wire.assembleEdges(edges)

    active_wires = [
        section_wire(
            loop,
            float(loop["h"]),
        )
        for loop in representative["loops"]
    ]
    blade_body = cq.Solid.makeLoft(active_wires, False)
    root_transition = cq.Solid.makeLoft(
        [
            section_wire(
                representative["loops"][0],
                -(root_lift + 0.2)
                / (tip_inlet_radius - hub_inlet_radius - root_lift),
                q_scale=1.35,
            ),
            active_wires[0],
        ],
        False,
    )
    blade = root_transition.fuse(blade_body)
    if not blade.isValid() or len(blade.Solids()) != 1:
        raise ValueError("representable Task 8 blade loft must be one valid solid")
    shape = _pattern_fuse(shape, blade, blade_count, phase_deg=0.0)
    if not shape.isValid() or len(shape.Solids()) != 1:
        raise ValueError("representable Task 8 fixture must be one valid solid")
    cq.exporters.export(shape, str(path), exportType="STEP")
    return path


def write_ambiguous_axis_step(path: Path) -> Path:
    import cadquery as cq

    axial_z = cq.Workplane("XY").workplane(offset=-10.0).circle(5.0).extrude(20.0).val()
    axial_x = cq.Workplane("YZ").workplane(offset=-10.0).circle(5.0).extrude(20.0).val()
    cq.exporters.export(axial_z.fuse(axial_x), str(path), exportType="STEP")
    return path


def write_displaced_parallel_axis_step(path: Path) -> Path:
    import cadquery as cq

    left = (
        cq.Workplane("XY")
        .center(-8.0, 0.0)
        .circle(3.0)
        .extrude(12.0)
        .val()
    )
    right = (
        cq.Workplane("XY")
        .center(8.0, 0.0)
        .circle(3.0)
        .extrude(12.0)
        .val()
    )
    bridge = (
        cq.Workplane("XY")
        .box(12.0, 2.0, 4.0)
        .translate((0.0, 0.0, 4.0))
        .val()
    )
    cq.exporters.export(left.fuse(bridge).fuse(right), str(path), exportType="STEP")
    return path


def write_open_section_loop_step(path: Path) -> Path:
    import cadquery as cq

    source_solid = (
        cq.Workplane("XY")
        .box(4.0, 2.0, 2.0)
        .translate((10.0, 0.0, 1.0))
        .val()
    )
    cq.exporters.export(source_solid, str(path), exportType="STEP")
    return path


def axis_first_fixture_expectations(
    *,
    blade_count: int = 8,
    splitter_count: int = 0,
    splitter_phase_fraction: float = 0.37,
    closed_shroud: bool = False,
    root_blend_radius_mm: float = 0.0,
) -> dict:
    return {
        "axis": {
            "origin_mm": [0.0, 0.0, 0.0],
            "direction": [0.0, 0.0, 1.0],
        },
        "hub_profile_rz_mm": [[4.0, 0.0], [32.0, 0.0], [32.0, 0.8]],
        "tip_profile_rz_mm": [[31.0, 0.6], [31.0, 7.8]],
        "main_blade_count": int(blade_count),
        "splitter_blade_count": int(splitter_count),
        "main_pitch_deg": 360.0 / blade_count,
        "splitter_phase_deg": splitter_phase_fraction * (360.0 / blade_count)
        if splitter_count
        else None,
        "topology": "closed" if closed_shroud else "open",
        "main_section_thickness_mm": {"root": 2.7, "tip": 1.24},
        "root_lift_mm": float(root_blend_radius_mm),
        "root_attachment_width_mm": 2.7,
        "root_blend_radius_mm": float(root_blend_radius_mm),
        "root_blend_geometry": (
            "blade_to_hub_attachment_fillet"
            if root_blend_radius_mm > 0.0
            else "sharp_blade_to_hub_attachment"
        ),
    }


def _variable_thickness_blade(
    cq,
    *,
    root_radius: float,
    tip_radius: float,
    root_half_width: float = 1.35,
    tip_half_width: float = 0.62,
    height: float,
    z_offset: float = 0.0,
):
    profile = (
        cq.Workplane("XY")
        .polyline(
            [
                (root_radius, -root_half_width),
                (tip_radius, -tip_half_width),
                (tip_radius, tip_half_width),
                (root_radius, root_half_width),
            ]
        )
        .close()
        .extrude(height)
    )
    if z_offset:
        profile = profile.translate((0.0, 0.0, z_offset))
    return profile.val()


def _pattern_fuse(shape, blade, count: int, *, phase_deg: float):
    for index in range(count):
        shape = shape.fuse(
            blade.rotate(
                (0.0, 0.0, 0.0),
                (0.0, 0.0, 1.0),
                phase_deg + 360.0 * index / count,
            )
        )
    return shape


def _fillet_blade_hub_attachment_edges(
    shape, *, radius_mm: float, hub_top_z: float
):
    attachment_edges = [
        edge
        for edge in shape.Edges()
        if edge.geomType() == "LINE"
        and edge.Length() > 4.0
        and all(
            abs(vertex.Center().z - float(hub_top_z)) <= 1.0e-7
            for vertex in edge.Vertices()
        )
    ]
    if not attachment_edges:
        raise ValueError("root-blend fixture has no blade-to-hub attachment edges")
    return shape.fillet(float(radius_mm), attachment_edges)


def write_offset_triangle_stl(path: Path, *, offset_z: float = 0.0) -> Path:
    from part_rule_synthesis.impeller_v11_6_deviation import (
        TriangleMesh,
        write_binary_stl,
    )
    import numpy as np

    mesh = TriangleMesh(
        vertices=np.asarray(
            [[0.0, 0.0, offset_z], [1.0, 0.0, offset_z], [0.0, 1.0, offset_z]],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2]], dtype=np.int32),
        normals=np.asarray([[0.0, 0.0, 1.0]], dtype=float),
    )
    write_binary_stl(path, mesh)
    return path
