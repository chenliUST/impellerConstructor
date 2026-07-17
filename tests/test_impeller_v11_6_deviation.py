from __future__ import annotations

# ruff: noqa: E402

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
    TriangleSurfaceIndex,
    _nearest_triangle_surface_distances,
    _point_to_triangles_distance,
    combine_triangle_meshes,
    compare_corresponding_mesh_regions,
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


def test_corresponding_region_comparison_cannot_match_a_different_surface_family():
    source_hub = _triangle_mesh(z=0.0)
    source_blade = _triangle_mesh(z=100.0)
    reconstruction_hub = _triangle_mesh(z=99.0)
    reconstruction_blade = _triangle_mesh(z=1.0)

    metrics, heatmap = compare_corresponding_mesh_regions(
        {
            "hub_flowpath": (source_hub, reconstruction_hub),
            "blade_surface_family": (source_blade, reconstruction_blade),
        }
    )

    assert metrics["comparison_direction"] == (
        "reconstruction_samples_to_corresponding_source_triangle_surfaces"
    )
    assert metrics["reconstruction_to_corresponding_source"]["minimum_mm"] == pytest.approx(99.0)
    assert "bidirectional" not in metrics
    assert metrics["contract_id"] == (
        "impeller_v1_1_6_corresponding_surface_deviation_v5"
    )
    assert metrics["symmetric_corresponding_sample_distribution"]["maximum_mm"] >= 99.0
    assert metrics["regions"]["hub_flowpath"][
        "reconstruction_to_corresponding_source"
    ]["rms_mm"] == pytest.approx(99.0)
    assert set(heatmap["triangle_regions"]) == {"hub_flowpath", "blade_surface_family"}
    assert heatmap["contract_id"] == "impeller_v1_1_6_deviation_heatmap_v2"
    assert heatmap["legend"]["units"] == "mm"


def test_symmetric_corresponding_distribution_weights_directions_equally():
    source = _repeated_triangle_mesh(z=0.0, count=9)
    reconstruction = combine_triangle_meshes(
        [_triangle_mesh(z=2.0), _translated_triangle_mesh(x=100.0, z=20.0)]
    )

    metrics, _ = compare_corresponding_mesh_regions(
        {"blade_sides::main_instance_0000": (source, reconstruction)}
    )

    symmetric = metrics["symmetric_corresponding_sample_distribution"]
    forward = metrics["reconstruction_to_corresponding_source"]
    reverse = metrics["corresponding_source_to_reconstruction"]
    assert symmetric["directional_aggregation"] == {
        "method": "independent_directional_statistics_fixed_weights",
        "reconstruction_to_source_weight": 0.5,
        "source_to_reconstruction_weight": 0.5,
    }
    assert symmetric["rms_mm"] == pytest.approx(
        math.sqrt(0.5 * forward["rms_mm"] ** 2 + 0.5 * reverse["rms_mm"] ** 2)
    )
    assert forward["median_mm"] > reverse["median_mm"] + 10.0
    assert symmetric["median_mm"] == pytest.approx(
        0.5 * forward["median_mm"] + 0.5 * reverse["median_mm"]
    )


def test_corresponding_distance_is_measured_to_triangle_interior_not_vertices():
    source = TriangleMesh(
        vertices=np.asarray(
            [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]],
            dtype=float,
        ),
        triangles=np.asarray([[0, 1, 2]], dtype=np.int32),
        normals=np.asarray([[0.0, 0.0, 1.0]], dtype=float),
    )
    samples = np.asarray([[2.0, 2.0, 1.0], [3.0, 3.0, 2.5]], dtype=float)

    distances = _nearest_triangle_surface_distances(samples, source)

    assert distances == pytest.approx([1.0, 2.5], abs=1.0e-9)


def test_accelerated_triangle_surface_distance_matches_exhaustive_search():
    rng = np.random.default_rng(116)
    vertex_count = 90
    vertices = rng.normal(size=(vertex_count, 3))
    triangles = np.arange(vertex_count, dtype=np.int32).reshape(-1, 3)
    mesh = TriangleMesh(
        vertices=vertices,
        triangles=triangles,
        normals=np.tile([[0.0, 0.0, 1.0]], (len(triangles), 1)),
    )
    samples = rng.normal(size=(80, 3))

    accelerated = _nearest_triangle_surface_distances(samples, mesh)
    triangle_points = vertices[triangles]
    exhaustive = np.asarray(
        [
            float(np.min(_point_to_triangles_distance(sample, triangle_points)))
            for sample in samples
        ]
    )

    assert accelerated == pytest.approx(exhaustive, abs=1.0e-10)


def test_reusable_triangle_surface_index_matches_exhaustive_search():
    rng = np.random.default_rng(11614)
    vertices = rng.normal(size=(150, 3))
    triangles = np.arange(len(vertices), dtype=np.int32).reshape(-1, 3)
    mesh = TriangleMesh(
        vertices=vertices,
        triangles=triangles,
        normals=np.tile([[0.0, 0.0, 1.0]], (len(triangles), 1)),
    )
    samples = rng.normal(size=(120, 3))

    index = TriangleSurfaceIndex.build(mesh)
    accelerated = index.distances(samples)
    triangle_points = vertices[triangles]
    exhaustive = np.asarray(
        [
            float(np.min(_point_to_triangles_distance(sample, triangle_points)))
            for sample in samples
        ]
    )

    assert accelerated == pytest.approx(exhaustive, abs=1.0e-10)


def test_corresponding_comparison_reuses_source_index_and_fuses_forward_queries():
    source = _repeated_triangle_mesh(z=0.0, count=12)
    first = _translated_triangle_mesh(x=0.1, z=0.25)
    second = _translated_triangle_mesh(x=0.2, z=0.5)
    execution_stats = {}

    metrics, heatmap = compare_corresponding_mesh_regions(
        {
            "surface_a": (source, first),
            "surface_b": (source, second),
        },
        execution_stats=execution_stats,
    )

    assert metrics["regions"]["surface_a"][
        "reconstruction_to_corresponding_source"
    ]["minimum_mm"] == pytest.approx(0.25)
    assert metrics["regions"]["surface_b"][
        "reconstruction_to_corresponding_source"
    ]["minimum_mm"] == pytest.approx(0.5)
    assert set(heatmap["triangle_regions"]) == {"surface_a", "surface_b"}
    assert execution_stats["surface_count"] == 2
    assert execution_stats["unique_source_index_count"] == 1
    assert execution_stats["unique_reconstruction_index_count"] == 2
    assert execution_stats["triangle_index_build_count"] == 3
    assert execution_stats["distance_query_count"] == 4
    assert execution_stats["legacy_distance_query_count"] == 6


def test_parallel_corresponding_comparison_is_numerically_identical_to_serial():
    source = _repeated_triangle_mesh(z=0.0, count=18)
    regions = {
        f"surface_{index}": (
            source,
            _translated_triangle_mesh(x=0.05 * index, z=0.2 + 0.1 * index),
        )
        for index in range(6)
    }
    serial_stats = {}
    parallel_stats = {}
    progress = []

    serial_metrics, serial_heatmap = compare_corresponding_mesh_regions(
        regions,
        max_workers=1,
        execution_stats=serial_stats,
    )
    parallel_metrics, parallel_heatmap = compare_corresponding_mesh_regions(
        regions,
        max_workers=4,
        execution_stats=parallel_stats,
        progress_callback=progress.append,
    )

    assert parallel_metrics == serial_metrics
    assert parallel_heatmap == serial_heatmap
    assert serial_stats["max_workers"] == 1
    assert parallel_stats["max_workers"] == 4
    assert parallel_stats["triangle_index_build_count"] == 7
    assert sorted(item["completed_surface_count"] for item in progress) == list(
        range(1, 7)
    )
    assert all(item["total_surface_count"] == 6 for item in progress)


def test_exact_surface_checkpoints_are_reused_without_recomputing_distances(
    tmp_path,
):
    source = _repeated_triangle_mesh(z=0.0, count=15)
    regions = {
        "surface_a": (source, _translated_triangle_mesh(x=0.1, z=0.3)),
        "surface_b": (source, _translated_triangle_mesh(x=0.2, z=0.6)),
    }
    first_stats = {}
    second_stats = {}

    first_metrics, first_heatmap = compare_corresponding_mesh_regions(
        regions,
        max_workers=2,
        checkpoint_dir=tmp_path / "checkpoints",
        execution_stats=first_stats,
    )
    second_metrics, second_heatmap = compare_corresponding_mesh_regions(
        regions,
        max_workers=2,
        checkpoint_dir=tmp_path / "checkpoints",
        execution_stats=second_stats,
    )

    assert second_metrics == first_metrics
    assert second_heatmap == first_heatmap
    assert first_stats["checkpoint_hit_count"] == 0
    assert first_stats["checkpoint_write_count"] == 2
    assert second_stats["checkpoint_hit_count"] == 2
    assert second_stats["checkpoint_write_count"] == 0
    assert second_stats["triangle_index_build_count"] == 0
    assert second_stats["distance_query_count"] == 0


def test_surface_checkpoint_invalidates_only_the_changed_geometry(tmp_path):
    source = _repeated_triangle_mesh(z=0.0, count=15)
    original_regions = {
        "surface_a": (source, _translated_triangle_mesh(x=0.1, z=0.3)),
        "surface_b": (source, _translated_triangle_mesh(x=0.2, z=0.6)),
    }
    compare_corresponding_mesh_regions(
        original_regions,
        max_workers=2,
        checkpoint_dir=tmp_path / "checkpoints",
    )
    changed_regions = {
        **original_regions,
        "surface_b": (source, _translated_triangle_mesh(x=0.2, z=0.7)),
    }
    stats = {}

    compare_corresponding_mesh_regions(
        changed_regions,
        max_workers=2,
        checkpoint_dir=tmp_path / "checkpoints",
        execution_stats=stats,
    )

    assert stats["checkpoint_hit_count"] == 1
    assert stats["checkpoint_write_count"] == 1
    assert stats["pending_surface_count"] == 1
    assert stats["triangle_index_build_count"] == 2
    assert stats["distance_query_count"] == 2


def test_parallel_partial_checkpoint_submits_only_changed_surfaces(tmp_path):
    source = _repeated_triangle_mesh(z=0.0, count=15)
    original_regions = {
        f"surface_{index}": (
            source,
            _translated_triangle_mesh(x=0.1 * index, z=0.2 * index),
        )
        for index in range(3)
    }
    compare_corresponding_mesh_regions(
        original_regions,
        max_workers=2,
        checkpoint_dir=tmp_path / "checkpoints",
    )
    changed_regions = {
        **original_regions,
        "surface_1": (source, _translated_triangle_mesh(x=0.1, z=0.25)),
        "surface_2": (source, _translated_triangle_mesh(x=0.2, z=0.45)),
    }
    stats = {}

    compare_corresponding_mesh_regions(
        changed_regions,
        max_workers=2,
        checkpoint_dir=tmp_path / "checkpoints",
        execution_stats=stats,
    )

    assert stats["checkpoint_hit_count"] == 1
    assert stats["pending_surface_count"] == 2
    assert stats["checkpoint_write_count"] == 2
    assert stats["max_workers"] == 2


def _triangle_mesh(*, z):
    return TriangleMesh(
        vertices=np.asarray([[0.0, 0.0, z], [1.0, 0.0, z], [0.0, 1.0, z]], dtype=float),
        triangles=np.asarray([[0, 1, 2]], dtype=np.int32),
        normals=np.asarray([[0.0, 0.0, 1.0]], dtype=float),
    )


def _translated_triangle_mesh(*, x, z):
    mesh = _triangle_mesh(z=z)
    return TriangleMesh(
        vertices=mesh.vertices + np.asarray([x, 0.0, 0.0]),
        triangles=mesh.triangles.copy(),
        normals=mesh.normals.copy(),
    )


def _repeated_triangle_mesh(*, z, count):
    vertices = []
    triangles = []
    for index in range(count):
        start = len(vertices)
        x = 0.01 * index
        vertices.extend([[x, 0.0, z], [x + 1.0, 0.0, z], [x, 1.0, z]])
        triangles.append([start, start + 1, start + 2])
    return TriangleMesh(
        vertices=np.asarray(vertices, dtype=float),
        triangles=np.asarray(triangles, dtype=np.int32),
        normals=np.tile([[0.0, 0.0, 1.0]], (count, 1)),
    )
