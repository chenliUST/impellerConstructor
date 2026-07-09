from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_2_g2_edge_surface import build_v10_2_g2_edge_surface


def _synthetic_frames(*, zero_curvature: bool = False, alternating: bool = False):
    pressure_frames = []
    suction_frames = []
    for index in range(5):
        x = float(index * 10)
        normal_sign = -1.0 if alternating and index % 2 else 1.0
        tangent_sign = -1.0 if alternating and index % 2 else 1.0
        curvature = [0.0, 0.0, 0.0] if zero_curvature else [0.0, 0.0, 1.0]
        pressure_frames.append(
            {
                "point": [x, 0.0, 0.0],
                "edge_tangent": [tangent_sign, 0.0, 0.0],
                "cross_edge_tangent": [0.0, 1.0, 0.0],
                "material_normal": [0.0, 0.0, normal_sign],
                "curvature_proxy": curvature,
            }
        )
        suction_frames.append(
            {
                "point": [x, 20.0, 0.0],
                "edge_tangent": [tangent_sign, 0.0, 0.0],
                "cross_edge_tangent": [0.0, -1.0, 0.0],
                "material_normal": [0.0, 0.0, normal_sign],
                "curvature_proxy": curvature,
            }
        )
    return pressure_frames, suction_frames


def _build_surface(*, radius_mm: float = 34.0, sample_count: int = 17, **frame_kwargs):
    pressure_frames, suction_frames = _synthetic_frames(**frame_kwargs)
    return build_v10_2_g2_edge_surface(
        surface_id="blade_0_leading_edge_surface",
        face_family="blade_leading_edge",
        role="leading_edge_g2_surface",
        pressure_frames=pressure_frames,
        suction_frames=suction_frames,
        radius_mm=radius_mm,
        sample_count=sample_count,
    )


def _distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(first, second)))


def _midpoint(first: list[float], second: list[float]) -> list[float]:
    return [(float(a) + float(b)) * 0.5 for a, b in zip(first, second)]


def test_v10_2_g2_edge_surface_builds_curved_synthetic_sections():
    surface = _build_surface(radius_mm=34.0, sample_count=17)

    quality = surface["transition_quality"]
    assert surface["kind"] == "native_topology_face"
    assert surface["degree_u"] == 3
    assert surface["degree_v"] == 4
    assert surface["short_direction_basis"] == "quartic_bezier_review_grid"
    assert quality["continuity_claim"] == "G2_TARGET_REVIEW_GRADE"
    assert quality["short_direction_sample_count"] == 17
    assert quality["short_direction_control_count"] >= 5
    assert len(surface["uv_grid"]) == 5
    assert all(len(section) == 17 for section in surface["uv_grid"])
    assert quality["min_midpoint_bulge_mm"] >= max(1.0, 0.12 * 34.0)
    assert quality["foldover_count"] == 0

    pressure_frames, suction_frames = _synthetic_frames()
    for index, section in enumerate(surface["uv_grid"]):
        assert section[0] == pressure_frames[index]["point"]
        assert section[-1] == suction_frames[index]["point"]


def test_v10_2_g2_edge_surface_keeps_material_bulge_when_curvature_proxies_are_zero():
    radius = 34.0
    surface = _build_surface(radius_mm=radius, zero_curvature=True)

    quality = surface["transition_quality"]
    assert quality["zero_curvature_proxy_input"] is True
    midpoint_sample = surface["uv_grid"][2][len(surface["uv_grid"][2]) // 2]
    chord_midpoint = _midpoint(surface["uv_grid"][2][0], surface["uv_grid"][2][-1])
    assert _distance(midpoint_sample, chord_midpoint) >= max(1.0, 0.12 * radius)


def test_v10_2_g2_edge_surface_midpoint_bulge_keeps_strict_threshold_after_rounding():
    radius = 673.7796317025164
    surface = _build_surface(radius_mm=radius, zero_curvature=True)

    midpoint_sample = surface["uv_grid"][2][len(surface["uv_grid"][2]) // 2]
    chord_midpoint = _midpoint(surface["uv_grid"][2][0], surface["uv_grid"][2][-1])
    assert _distance(midpoint_sample, chord_midpoint) >= max(1.0, 0.12 * radius)


def test_v10_2_g2_edge_surface_rejects_short_direction_sample_count_below_17():
    pressure_frames, suction_frames = _synthetic_frames()

    with pytest.raises(ValueError, match="sample_count"):
        build_v10_2_g2_edge_surface(
            surface_id="blade_0_tip_surface",
            face_family="blade_tip",
            role="open_tip_g2_surface",
            pressure_frames=pressure_frames,
            suction_frames=suction_frames,
            radius_mm=34.0,
            sample_count=16,
        )


def test_v10_2_g2_edge_surface_rejects_frame_count_mismatch():
    pressure_frames, suction_frames = _synthetic_frames()

    with pytest.raises(ValueError, match="frame count"):
        build_v10_2_g2_edge_surface(
            surface_id="blade_0_trailing_edge_surface",
            face_family="blade_trailing_edge",
            role="trailing_edge_g2_surface",
            pressure_frames=pressure_frames,
            suction_frames=suction_frames[:-1],
            radius_mm=34.0,
        )


def test_v10_2_g2_edge_surface_reports_flip_and_foldover_metrics():
    surface = _build_surface(alternating=True)

    quality = surface["transition_quality"]
    for key in [
        "max_section_tangent_flip_deg",
        "max_pressure_section_tangent_flip_deg",
        "max_suction_section_tangent_flip_deg",
        "max_normal_flip_deg",
        "max_pressure_normal_flip_deg",
        "max_suction_normal_flip_deg",
        "foldover_count",
    ]:
        assert key in quality
        assert isinstance(quality[key], (int, float))
    assert quality["max_section_tangent_flip_deg"] > 0.0
    assert quality["max_normal_flip_deg"] > 0.0


def test_v10_2_g2_edge_surface_reports_pressure_suction_normal_opposition():
    pressure_frames, suction_frames = _synthetic_frames()
    for pressure_frame, suction_frame in zip(pressure_frames, suction_frames):
        pressure_frame["material_normal"] = [0.0, 0.0, 1.0]
        suction_frame["material_normal"] = [0.0, 0.0, -1.0]

    surface = build_v10_2_g2_edge_surface(
        surface_id="blade_0_leading_edge_surface",
        face_family="blade_leading_edge",
        role="leading_edge_g2_surface",
        pressure_frames=pressure_frames,
        suction_frames=suction_frames,
        radius_mm=34.0,
    )

    quality = surface["transition_quality"]
    assert quality["max_pressure_vs_suction_normal_opposition_deg"] >= 179.0
    assert quality["degenerate_averaged_normal_count"] == len(pressure_frames)
    assert quality["max_normal_flip_deg"] >= 179.0


def test_v10_2_g2_edge_surface_rejects_negative_radius():
    pressure_frames, suction_frames = _synthetic_frames()

    with pytest.raises(ValueError, match="radius_mm"):
        build_v10_2_g2_edge_surface(
            surface_id="blade_0_tip_surface",
            face_family="blade_tip",
            role="open_tip_g2_surface",
            pressure_frames=pressure_frames,
            suction_frames=suction_frames,
            radius_mm=-0.001,
        )
