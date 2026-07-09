from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_3_blade_faces import build_blade_faces_from_section_lattice
from part_rule_synthesis.impeller_v10_3_root_blend import (
    _grid_foldover_count,
    _max_gap_to_hub,
    _max_grid_normal_flip,
    _max_inner_loop_gap,
    _max_width_tangent_flip,
    _min_signed_height_to_hub,
    _project_and_offset_root_loop,
    build_v10_3_root_blend,
)
from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice


SEGMENT_COMPONENTS = {
    "pressure_side": "pressure_root",
    "leading_edge": "leading_root_corner",
    "suction_side": "suction_root",
    "trailing_edge": "trailing_root_corner",
}


def _defaults() -> dict:
    return {
        "main_blade_count": 2,
        "splitter_blade_count": 2,
        "average_blade_thickness_mm": 32.0,
        "section_loop_sample_count": 17,
        "face_streamwise_sample_count": 5,
        "main_streamwise_start_u": 0.08,
        "main_streamwise_end_u": 0.92,
        "splitter_streamwise_start_u": 0.38,
        "splitter_streamwise_end_u": 0.88,
        "resolved_root_attachment_width_mm": 40.0,
        "resolved_root_attachment_lift_mm": 28.0,
        "attachment_short_direction_sample_count": 17,
    }


def _case() -> tuple[dict, list[dict], dict, dict]:
    defaults = _defaults()
    lattice = build_section_loop_lattice(parameters={}, defaults=defaults)
    assert lattice["status"] == "PASS"
    faces = build_blade_faces_from_section_lattice(lattice)
    assert faces["status"] == "PASS"
    return lattice, faces["surfaces"], _hub_surface(), defaults


def _hub_surface() -> dict:
    return {
        "id": "hub_revolve_surface",
        "profile_samples_rz": [
            {"r_mm": 47.0, "z_mm": 8.0},
            {"r_mm": 50.0, "z_mm": 10.0},
            {"r_mm": 54.0, "z_mm": 12.0},
            {"r_mm": 58.0, "z_mm": 14.0},
            {"r_mm": 67.0, "z_mm": 18.0},
        ],
    }


def _build_root(blade_index: int = 0, **overrides) -> dict:
    lattice, faces, hub, defaults = _case()
    return build_v10_3_root_blend(
        blade_index=blade_index,
        lattice=overrides.get("lattice", lattice),
        blade_faces=overrides.get("blade_faces", faces),
        hub_surface=overrides.get("hub_surface", hub),
        defaults=overrides.get("defaults", defaults),
    )


def _profile() -> list[tuple[float, float]]:
    return [(float(sample["r_mm"]), float(sample["z_mm"])) for sample in _hub_surface()["profile_samples_rz"]]


def _root_segments(lattice: dict, blade_index: int = 0) -> dict[str, list[list[float]]]:
    root_loop = lattice["blades"][blade_index]["section_loops"][0]
    return {
        segment_name: copy.deepcopy(root_loop["segments"][segment_name]["points"])
        for segment_name in SEGMENT_COMPONENTS
    }


def _closed_root_loop(lattice: dict, blade_index: int = 0) -> list[list[float]]:
    segments = _root_segments(lattice, blade_index)
    stitched = []
    for segment_name in ["pressure_side", "leading_edge", "suction_side", "trailing_edge"]:
        points = segments[segment_name]
        stitched.extend(points[1:] if stitched and stitched[-1] == points[0] else points)
    if stitched[0] != stitched[-1]:
        stitched.append(stitched[0])
    return stitched


def _radius(point: list[float]) -> float:
    return math.hypot(float(point[0]), float(point[1]))


def _hub_radius_at_z(hub_surface: dict, z: float) -> float:
    samples = sorted(
        [
            (float(sample.get("r_mm", sample.get("radius_mm"))), float(sample["z_mm"]))
            for sample in hub_surface["profile_samples_rz"]
        ],
        key=lambda sample: sample[1],
    )
    for radius, sample_z in samples:
        if abs(z - sample_z) <= 1.0e-9:
            return radius
    for (left_radius, left_z), (right_radius, right_z) in zip(samples, samples[1:]):
        if left_z <= z <= right_z:
            t = (z - left_z) / (right_z - left_z)
            return left_radius * (1.0 - t) + right_radius * t
    raise AssertionError(f"z outside hub profile: {z}")


def _distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((float(left) - float(right)) ** 2 for left, right in zip(first, second)))


def _signed_height(point: list[float], hub_surface: dict) -> float:
    return _radius(point) - _hub_radius_at_z(hub_surface, point[2])


def _centroid(points: list[list[float]]) -> list[float]:
    open_points = points[:-1] if points and points[0] == points[-1] else points
    return [
        sum(point[axis] for point in open_points) / len(open_points)
        for axis in range(2)
    ]


def test_root_blend_builds_four_visible_components_per_blade():
    root = _build_root()

    assert root["status"] == "PASS"
    assert root["id"] == "blade_0_root_annular_surface"
    assert root["display"]["visible_by_default"] is False
    assert root["display"]["inspection_class"] == "root_to_hub_blend"
    assert root["display"]["color"] == "#ff00cc"
    assert root["display"]["wire_color"] == "#fff200"
    assert root["root_blend_method"] == "section-loop-driven segmented support-domain Hermite/G2 root blend"

    components = root["component_surfaces"]
    assert [component["component_segment"] for component in components] == list(SEGMENT_COMPONENTS.values())
    assert len(components) == 4
    for component in components:
        assert component["component_of"] == "blade_0_root_annular_surface"
        assert component["display"]["visible_by_default"] is True
        assert component["display"]["inspection_class"] == "root_to_hub_blend"
        assert component["display"]["color"] == "#ff00cc"
        assert component["display"]["wire_color"] == "#fff200"
        assert component["uv_grid"]
        assert component["edge_samples"]
        assert component["wireframe"] == {"enabled": True, "source": "uv_grid"}
        assert component["mesh"]["strategy"] == "v1_0_3_segmented_root_blend_compact_quad_mesh"
        assert component["mesh"]["quad_count"] > 0
        assert component["root_blend_quality"]["component_status"] == "PASS"
        assert component["transition_quality"]["foldover_count"] == 0


def test_root_blend_public_api_accepts_positional_and_keyword_calls():
    lattice, faces, hub, defaults = _case()

    positional = build_v10_3_root_blend(0, lattice, faces, hub, defaults)
    keyword = build_v10_3_root_blend(
        blade_index=0,
        lattice=lattice,
        blade_faces=faces,
        hub_surface=hub,
        defaults=defaults,
    )

    assert positional["status"] == "PASS"
    assert positional["edge_samples"]["blade_inner_loop"] == keyword["edge_samples"]["blade_inner_loop"]
    assert positional["root_blend_quality"]["winding_orientation"] == keyword["root_blend_quality"]["winding_orientation"]


def test_inner_loop_matches_blade_root_loop_exactly_and_aggregate_is_hidden():
    lattice, faces, hub, defaults = _case()
    root = build_v10_3_root_blend(
        blade_index=0,
        lattice=lattice,
        blade_faces=faces,
        hub_surface=hub,
        defaults=defaults,
    )

    assert root["display"]["visible_by_default"] is False
    assert root["edge_samples"]["blade_inner_loop"] == _closed_root_loop(lattice)
    for source_segment, component_name in SEGMENT_COMPONENTS.items():
        component = next(
            surface for surface in root["component_surfaces"] if surface["component_segment"] == component_name
        )
        assert component["edge_samples"]["blade_inner_loop"] == _root_segments(lattice)[source_segment]
        assert component["uv_grid"][-1] == _root_segments(lattice)[source_segment]

    quality = root["root_blend_quality"]
    assert quality["max_root_inner_loop_gap_mm"] <= 1.0e-6
    assert quality["component_count"] == 4


def test_root_components_stay_on_material_side_and_do_not_fold():
    lattice, faces, hub, defaults = _case()
    root = build_v10_3_root_blend(
        blade_index=0,
        lattice=lattice,
        blade_faces=faces,
        hub_surface=hub,
        defaults=defaults,
    )

    assert root["root_blend_quality"]["foldover_count"] == 0
    assert root["root_blend_quality"]["min_signed_height_to_hub_mm"] >= -1.0e-6
    assert root["root_blend_quality"]["max_tangent_flip_deg"] < 45.0
    assert root["root_blend_quality"]["max_normal_flip_deg"] < 45.0
    assert root["root_blend_quality"]["min_effective_root_width_mm"] >= 20.0

    by_segment = {component["component_segment"]: component for component in root["component_surfaces"]}
    for component_name in ["pressure_root", "suction_root"]:
        component = by_segment[component_name]
        measured_min_height = min(_signed_height(point, hub) for row in component["uv_grid"] for point in row)
        assert component["root_blend_quality"]["min_signed_height_to_hub_mm"] == pytest.approx(
            measured_min_height,
            abs=1.0e-9,
        )
        assert measured_min_height >= -1.0e-6
    for component in root["component_surfaces"]:
        quality = component["transition_quality"]
        assert quality["foldover_count"] == 0
        assert quality["max_tangent_flip_deg"] < 45.0
        assert quality["max_normal_flip_deg"] < 45.0


def test_root_outer_loop_is_hub_domain_offset_not_local_cross_product():
    lattice, faces, hub, defaults = _case()
    root = build_v10_3_root_blend(
        blade_index=0,
        lattice=lattice,
        blade_faces=faces,
        hub_surface=hub,
        defaults=defaults,
    )

    quality = root["root_blend_quality"]
    assert quality["projection_rule"] == "hub_theta_z_parameter_domain"
    assert quality["offset_rule"] == "closed_footprint_winding_support_domain_offset"
    assert quality["domain_bracket_failure_count"] == 0
    assert quality["support_domain_violation_count"] == 0
    assert quality["max_projection_residual_mm"] <= 1.0e-6
    assert quality["max_root_outer_loop_gap_to_hub_mm"] <= 1.0e-6
    assert quality["winding_orientation"] in {"ccw", "cw"}
    assert quality["offset_self_intersection_count"] == 0

    projected = root["edge_samples"]["projected_footprint_loop"]
    outer = root["edge_samples"]["hub_outer_loop"]
    assert len(projected) == len(outer)
    assert any(abs(float(projected_point[2]) - float(outer_point[2])) > 1.0e-6 for projected_point, outer_point in zip(projected, outer))
    for outer_point in outer:
        assert _radius(outer_point) == pytest.approx(_hub_radius_at_z(hub, outer_point[2]), abs=1.0e-6)


def test_winding_orientation_drives_support_domain_offset_direction():
    root_loop = [
        [65.0, 0.0, 10.0],
        [64.980000, 1.612000, 10.0],
        [64.960000, 1.612000, 12.0],
        [64.940000, 0.0, 12.0],
        [65.0, 0.0, 10.0],
    ]
    reversed_loop = [root_loop[0], *list(reversed(root_loop[1:-1])), root_loop[0]]

    ccw = _project_and_offset_root_loop(
        root_loop=root_loop,
        profile=_profile(),
        width_mm=4.0,
        z_tolerance_mm=0.0,
    )
    cw = _project_and_offset_root_loop(
        root_loop=reversed_loop,
        profile=_profile(),
        width_mm=4.0,
        z_tolerance_mm=0.0,
    )

    assert ccw["status"] == "PASS"
    assert cw["status"] == "PASS"
    assert ccw["winding_orientation"] != cw["winding_orientation"]
    for result in [ccw, cw]:
        centroid = _centroid(result["domain_loop"])
        offset_delta = [
            result["outer_domain_loop"][0][axis] - result["domain_loop"][0][axis]
            for axis in range(2)
        ]
        away_from_centroid = [
            result["domain_loop"][0][axis] - centroid[axis]
            for axis in range(2)
        ]
        assert offset_delta[0] * away_from_centroid[0] + offset_delta[1] * away_from_centroid[1] > 0.0


def test_default_support_domain_offset_moves_representative_samples_away_from_centroid():
    root = _build_root()
    domain_loop = root["root_blend_quality"]["support_domain_loop"]
    outer_domain_loop = root["root_blend_quality"]["support_outer_domain_loop"]
    centroid = _centroid(domain_loop)

    for index in [0, len(domain_loop) // 4, len(domain_loop) // 2]:
        offset_delta = [
            outer_domain_loop[index][axis] - domain_loop[index][axis]
            for axis in range(2)
        ]
        away_from_centroid = [
            domain_loop[index][axis] - centroid[axis]
            for axis in range(2)
        ]
        assert offset_delta[0] * away_from_centroid[0] + offset_delta[1] * away_from_centroid[1] > 0.0


def test_projection_metrics_present_and_widths_are_effective():
    root = _build_root()
    quality = root["root_blend_quality"]

    for metric in [
        "max_projection_residual_mm",
        "domain_bracket_success_count",
        "domain_bracket_failure_count",
        "support_z_clamp_count",
        "support_domain_violation_count",
        "root_width_request_mm",
        "min_effective_root_width_mm",
        "max_effective_root_width_mm",
        "winding_orientation",
        "offset_self_intersection_count",
    ]:
        assert metric in quality

    assert quality["root_width_request_mm"] == 40.0
    assert quality["min_effective_root_width_mm"] >= 0.5 * quality["root_width_request_mm"]
    assert quality["max_effective_root_width_mm"] >= quality["min_effective_root_width_mm"]


def test_quality_gap_helpers_measure_nonzero_inner_and_outer_perturbations():
    lattice, faces, hub, defaults = _case()
    root = build_v10_3_root_blend(0, lattice, faces, hub, defaults)
    source_loop = _closed_root_loop(lattice)
    perturbed_inner = copy.deepcopy(root["edge_samples"]["blade_inner_loop"])
    perturbed_inner[3][0] += 0.125
    perturbed_outer = copy.deepcopy(root["edge_samples"]["hub_outer_loop"])
    perturbed_outer[4][0] += 0.25

    assert root["root_blend_quality"]["max_root_inner_loop_gap_mm"] == pytest.approx(
        _max_inner_loop_gap(root["edge_samples"]["blade_inner_loop"], source_loop),
        abs=1.0e-9,
    )
    assert _max_inner_loop_gap(perturbed_inner, source_loop) > 0.1
    assert root["root_blend_quality"]["max_root_outer_loop_gap_to_hub_mm"] == pytest.approx(
        _max_gap_to_hub(root["edge_samples"]["hub_outer_loop"], hub),
        abs=1.0e-9,
    )
    assert _max_gap_to_hub(perturbed_outer, hub) > 0.1


def test_grid_foldover_detection_catches_crossed_root_component_grid():
    folded_grid = [
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        [[1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        [[0.0, 2.0, 0.0], [1.0, 2.0, 0.0]],
    ]

    assert _grid_foldover_count(folded_grid) > 0


def test_grid_foldover_detection_catches_bow_tie_and_collapsed_cells():
    bow_tie_grid = [
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
        [[0.0, 1.0, 0.0], [2.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
    ]
    collapsed_grid = [
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
    ]

    assert _grid_foldover_count(bow_tie_grid) > 0
    assert _grid_foldover_count(collapsed_grid) > 0


def test_grid_normal_flip_uses_raw_adjacent_normal_reversal():
    reversing_grid = [
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
    ]

    assert _max_grid_normal_flip(reversing_grid) >= 179.0


def test_width_tangent_flip_treats_zero_length_steps_as_failure_signal():
    zero_step_grid = [
        [[0.0, 0.0, 0.0]],
        [[0.0, 0.0, 0.0]],
        [[0.0, 1.0, 0.0]],
    ]

    assert _max_width_tangent_flip(zero_step_grid) >= 180.0


def test_self_intersecting_root_segment_fails_as_foldover_or_material_side():
    lattice, _faces, hub, defaults = _case()
    broken = copy.deepcopy(lattice)
    pressure = broken["blades"][0]["section_loops"][0]["segments"]["pressure_side"]["points"]
    pressure[4], pressure[12] = pressure[12], pressure[4]
    faces = build_blade_faces_from_section_lattice(broken)
    assert faces["status"] == "PASS"

    root = build_v10_3_root_blend(0, broken, faces["surfaces"], hub, defaults)

    assert root["status"] == "FAIL"
    assert root["root_blend_quality"]["reason"] in {
        "v1_0_3_root_segment_foldover",
        "v1_0_3_root_material_side_ambiguous",
    }


def test_signed_height_metric_includes_every_blend_grid_sample_and_rejects_under_hub_samples():
    lattice, faces, hub, defaults = _case()
    root = build_v10_3_root_blend(0, lattice, faces, hub, defaults)
    all_component_points = [
        point
        for component in root["component_surfaces"]
        for row in component["uv_grid"]
        for point in row
    ]
    measured_min_height = min(_signed_height(point, hub) for point in all_component_points)
    under_hub_points = copy.deepcopy(all_component_points[:])
    under_hub_points[0][0] = 0.5 * under_hub_points[0][0]
    under_hub_points[0][1] = 0.5 * under_hub_points[0][1]

    assert root["root_blend_quality"]["min_signed_height_to_hub_mm"] == pytest.approx(
        measured_min_height,
        abs=1.0e-9,
    )
    assert measured_min_height >= -1.0e-6
    assert _min_signed_height_to_hub(under_hub_points, _profile()) < -1.0


def test_root_blend_rejects_under_hub_root_loop_with_signed_height_failure():
    lattice, _faces, hub, defaults = _case()
    inflated_hub = copy.deepcopy(hub)
    for sample in inflated_hub["profile_samples_rz"]:
        sample["r_mm"] += 40.0
    faces = build_blade_faces_from_section_lattice(lattice)

    root = build_v10_3_root_blend(0, lattice, faces["surfaces"], inflated_hub, defaults)

    assert root["status"] == "FAIL"
    assert root["root_blend_quality"]["reason"] == "v1_0_3_root_signed_height_failed"


def test_quality_gate_failure_preserves_measured_failing_metrics():
    lattice, _faces, hub, defaults = _case()
    inflated_hub = copy.deepcopy(hub)
    for sample in inflated_hub["profile_samples_rz"]:
        sample["r_mm"] += 40.0
    faces = build_blade_faces_from_section_lattice(lattice)

    root = build_v10_3_root_blend(0, lattice, faces["surfaces"], inflated_hub, defaults)

    assert root["status"] == "FAIL"
    assert root["root_blend_quality"]["reason"] == "v1_0_3_root_signed_height_failed"
    assert root["root_blend_quality"]["min_signed_height_to_hub_mm"] < -1.0
    assert root["root_blend_quality"]["domain_bracket_success_count"] > 0
    assert root["root_blend_quality"]["component_count"] == 4


def test_synthetic_suction_loop_reversal_is_rejected():
    lattice, faces, hub, defaults = _case()
    broken = copy.deepcopy(lattice)
    broken["blades"][0]["section_loops"][0]["segments"]["suction_side"]["points"] = list(
        reversed(broken["blades"][0]["section_loops"][0]["segments"]["suction_side"]["points"])
    )

    root = build_v10_3_root_blend(
        blade_index=0,
        lattice=broken,
        blade_faces=faces,
        hub_surface=hub,
        defaults=defaults,
    )

    assert root["status"] == "FAIL"
    assert root["root_blend_quality"]["reason"] in {
        "v1_0_3_root_material_side_ambiguous",
        "v1_0_3_root_component_gap",
        "v1_0_3_root_segment_foldover",
    }
    assert root["component_surfaces"] == []


@pytest.mark.parametrize(
    ("defaults_override", "hub_override", "expected_reason"),
    [
        ({"resolved_root_attachment_width_mm": 0.0}, None, "v1_0_3_root_footprint_offset_failed"),
        ({"attachment_short_direction_sample_count": 16}, None, "v1_0_3_root_segment_g2_infeasible"),
        (None, {"id": "hub_without_profile"}, "v1_0_3_root_projection_failed"),
        (None, {"id": "bad_profile", "profile_samples_rz": [{"r_mm": "bad", "z_mm": 1.0}]}, "v1_0_3_root_projection_failed"),
    ],
)
def test_malformed_defaults_hub_and_profile_fail_structured(defaults_override, hub_override, expected_reason):
    lattice, faces, hub, defaults = _case()
    if defaults_override:
        defaults = {**defaults, **defaults_override}
    if hub_override is not None:
        hub = hub_override

    root = build_v10_3_root_blend(
        blade_index=0,
        lattice=lattice,
        blade_faces=faces,
        hub_surface=hub,
        defaults=defaults,
    )

    assert root["status"] == "FAIL"
    assert root["root_blend_quality"]["reason"] == expected_reason
    assert root["uv_grid"] == []
    assert root["mesh"]["quad_count"] == 0
