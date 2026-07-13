from __future__ import annotations

from pathlib import Path


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


def write_offset_triangle_stl(path: Path, *, offset_z: float = 0.0) -> Path:
    from part_rule_synthesis.impeller_v11_6_deviation import TriangleMesh, write_binary_stl
    import numpy as np

    mesh = TriangleMesh(
        vertices=np.asarray([[0.0, 0.0, offset_z], [1.0, 0.0, offset_z], [0.0, 1.0, offset_z]], dtype=float),
        triangles=np.asarray([[0, 1, 2]], dtype=np.int32),
        normals=np.asarray([[0.0, 0.0, 1.0]], dtype=float),
    )
    write_binary_stl(path, mesh)
    return path
