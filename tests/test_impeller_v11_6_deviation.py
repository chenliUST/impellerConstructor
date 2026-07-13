from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from part_rule_synthesis.impeller_v11_6_deviation import (
    TriangleMesh,
    compare_meshes,
    read_stl,
    resolve_periodic_phase_alignment,
    transform_mesh,
)
from step_fixtures import write_offset_triangle_stl


def test_identical_meshes_have_zero_bidirectional_error(tmp_path):
    path = write_offset_triangle_stl(tmp_path / "same.stl")
    mesh = read_stl(path)
    metrics, heatmap = compare_meshes(mesh, mesh, source_closed=False, reconstruction_closed=False)

    assert metrics["bidirectional"]["maximum_mm"] == 0.0
    assert metrics["symmetric_chamfer_mm"] == 0.0
    assert metrics["signed_distance_available"] is False
    assert max(heatmap["errors_mm"]) == 0.0


def test_known_normal_offset_is_reported_in_numeric_and_heatmap_data(tmp_path):
    source = read_stl(write_offset_triangle_stl(tmp_path / "source.stl", offset_z=0.0))
    reconstruction = read_stl(write_offset_triangle_stl(tmp_path / "reconstruction.stl", offset_z=2.5))
    metrics, heatmap = compare_meshes(source, reconstruction, source_closed=False, reconstruction_closed=False)

    assert metrics["bidirectional"]["rms_mm"] == pytest.approx(2.5, abs=1.0e-6)
    assert metrics["semantic_triangle_coverage"] == 1.0
    assert heatmap["errors_mm"] == [2.5, 2.5, 2.5]
    assert heatmap["legend"]["p95_mm"] == 2.5


def test_periodic_phase_alignment_removes_only_rotation_about_confirmed_axis():
    blade_count = 8
    vertices = []
    triangles = []
    normals = []
    for index in range(blade_count):
        angle = 2.0 * math.pi * index / blade_count
        rotation = np.asarray(
            [[math.cos(angle), -math.sin(angle), 0.0], [math.sin(angle), math.cos(angle), 0.0], [0.0, 0.0, 1.0]]
        )
        start = len(vertices)
        local = np.asarray([[20.0, 0.0, 0.0], [24.0, 1.0, 0.4], [21.0, 3.0, 2.0]])
        vertices.extend((local @ rotation.T).tolist())
        triangles.append([start, start + 1, start + 2])
        normals.append([0.0, 0.0, 1.0])
    source = TriangleMesh(np.asarray(vertices), np.asarray(triangles), np.asarray(normals))
    imposed_phase_deg = 7.0
    angle = math.radians(imposed_phase_deg)
    reconstruction = transform_mesh(
        source,
        [
            [math.cos(angle), -math.sin(angle), 0.0, 0.0],
            [math.sin(angle), math.cos(angle), 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
    )

    aligned, evidence = resolve_periodic_phase_alignment(source, reconstruction, blade_count)
    metrics, _ = compare_meshes(source, aligned, source_closed=False, reconstruction_closed=False)

    assert evidence["method"] == "bounded_symmetric_periodic_phase_search"
    assert evidence["rotation_about_axis_deg"] == pytest.approx(-imposed_phase_deg, abs=0.15)
    assert evidence["scale"] == 1.0
    assert evidence["translation_mm"] == [0.0, 0.0, 0.0]
    assert evidence["primary_icp_applied"] is False
    assert metrics["bidirectional"]["maximum_mm"] < 0.1
