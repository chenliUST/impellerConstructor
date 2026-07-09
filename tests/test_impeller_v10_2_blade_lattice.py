from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from impeller_v10_2_historical_fixture import historical_v10_2_metadata
from part_rule_synthesis.impeller_v10_2_blade_lattice import (
    _frames_from_loop,
    build_v10_2_blade_lattice,
)


FRAME_GROUPS = [
    "leading_pressure_frames",
    "leading_suction_frames",
    "trailing_pressure_frames",
    "trailing_suction_frames",
    "tip_pressure_frames",
    "tip_suction_frames",
    "root_pressure_frames",
    "root_suction_frames",
]
FRAME_KEYS = {
    "point",
    "edge_tangent",
    "cross_edge_tangent",
    "material_normal",
    "curvature_proxy",
}
PRESERVED_LOOP_SOURCES = {
    "pressure_root_loop": ("blade_0_pressure_surface", "root_profile_pressure_edge"),
    "suction_root_loop": ("blade_0_suction_surface", "root_profile_suction_edge"),
    "pressure_tip_loop": ("blade_0_pressure_surface", "tip_profile_pressure_edge"),
    "suction_tip_loop": ("blade_0_suction_surface", "tip_profile_suction_edge"),
    "leading_pressure_loop": ("blade_0_leading_edge_surface", "pressure_side_leading_boundary"),
    "leading_suction_loop": ("blade_0_leading_edge_surface", "suction_side_leading_boundary"),
    "trailing_pressure_loop": ("blade_0_trailing_edge_surface", "pressure_side_trailing_boundary"),
    "trailing_suction_loop": ("blade_0_trailing_edge_surface", "suction_side_trailing_boundary"),
    "root_leading_cap": ("blade_0_leading_edge_surface", "root_profile_leading_cap"),
    "tip_leading_cap": ("blade_0_leading_edge_surface", "tip_profile_leading_cap"),
    "root_trailing_cap": ("blade_0_trailing_edge_surface", "root_profile_trailing_cap"),
    "tip_trailing_cap": ("blade_0_trailing_edge_surface", "tip_profile_trailing_cap"),
}


def _open_v10_surfaces() -> dict[str, dict]:
    metadata = historical_v10_2_metadata("radial_open_reference_v1_0")
    return {surface["id"]: surface for surface in metadata["surface_graph"]["surfaces"]}


def _dot(left: list[float], right: list[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _assert_no_consecutive_duplicate_points(loop: list[list[float]]) -> None:
    assert all(previous != current for previous, current in zip(loop, loop[1:]))


def test_v10_2_blade_lattice_preserves_exact_source_loops_and_closes_exterior_loops():
    surfaces = _open_v10_surfaces()

    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)

    assert lattice["status"] == "PASS"
    loops = lattice["loops"]
    for loop_name, (surface_id, edge_name) in PRESERVED_LOOP_SOURCES.items():
        assert loops[loop_name] == surfaces[surface_id]["edge_samples"][edge_name]

    closed_loops = lattice["closed_loops"]
    for loop_name in ["blade_exterior_root_loop", "blade_exterior_tip_loop"]:
        loop = closed_loops[loop_name]
        assert len(loop) >= 80
        assert loop[0] == loop[-1]


def test_v10_2_blade_lattice_closed_exterior_loops_have_no_consecutive_duplicate_points():
    surfaces = _open_v10_surfaces()

    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)

    assert lattice["status"] == "PASS"
    closed_loops = lattice["closed_loops"]
    for loop_name in ["blade_exterior_root_loop", "blade_exterior_tip_loop"]:
        loop = closed_loops[loop_name]
        assert len(loop) >= 80
        assert loop[0] == loop[-1]
        _assert_no_consecutive_duplicate_points(loop)


def test_v10_2_blade_lattice_returned_loops_do_not_alias_source_samples():
    surfaces = _open_v10_surfaces()
    for loop_name, (surface_id, edge_name) in PRESERVED_LOOP_SOURCES.items():
        lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)
        original_source_point = list(surfaces[surface_id]["edge_samples"][edge_name][0])

        assert lattice["status"] == "PASS"
        lattice["loops"][loop_name][0][0] += 1000.0
        assert surfaces[surface_id]["edge_samples"][edge_name][0] == original_source_point


def test_v10_2_blade_lattice_builds_derivative_frames_for_all_blade_edges():
    surfaces = _open_v10_surfaces()

    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)

    assert lattice["status"] == "PASS"
    frames = lattice["frames"]
    for frame_group in FRAME_GROUPS:
        assert len(frames[frame_group]) >= 17
        assert FRAME_KEYS <= set(frames[frame_group][0])


def test_v10_2_blade_lattice_material_normals_do_not_flip_between_adjacent_frames():
    surfaces = _open_v10_surfaces()

    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)

    assert lattice["status"] == "PASS"
    for frame_group in FRAME_GROUPS:
        normals = [frame["material_normal"] for frame in lattice["frames"][frame_group]]
        adjacent_dots = [
            _dot(previous, current)
            for previous, current in zip(normals, normals[1:])
        ]
        assert min(adjacent_dots) >= 0.0


def test_v10_2_blade_lattice_corrects_synthetic_180_degree_material_normal_flips():
    loop = [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [2.0, 0.0, 0.0],
        [3.0, 0.0, 0.0],
    ]
    adjacent_loop = [
        [0.0, 1.0, 0.0],
        [1.0, -1.0, 0.0],
        [2.0, 1.0, 0.0],
        [3.0, -1.0, 0.0],
    ]
    raw_normals = [
        [0.0, 0.0, 1.0],
        [0.0, 0.0, -1.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.0, -1.0],
    ]

    assert min(_dot(previous, current) for previous, current in zip(raw_normals, raw_normals[1:])) < 0.0
    frames = _frames_from_loop(loop, adjacent_loop)
    corrected_normals = [frame["material_normal"] for frame in frames]
    adjacent_dots = [
        _dot(previous, current)
        for previous, current in zip(corrected_normals, corrected_normals[1:])
    ]

    assert min(adjacent_dots) >= 0.0
