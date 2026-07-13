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
            "origin_mm": [0.0, 0.0, 8.0 if closed_shroud else 7.8],
            "direction": [0.0, 0.0, -1.0],
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
