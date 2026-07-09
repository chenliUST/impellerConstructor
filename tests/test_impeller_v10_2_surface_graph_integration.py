from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from impeller_v10_2_historical_fixture import (
    historical_v10_2_graph_tuple,
    historical_v10_2_runtime,
)
from part_rule_synthesis.impeller_v10_surface_graph import build_v10_surface_graph
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata, _geometry_validity_metadata


def _distance(first: list[float], second: list[float]) -> float:
    return sum((float(left) - float(right)) ** 2 for left, right in zip(first, second)) ** 0.5


def _column(grid: list[list[list[float]]], index: int) -> list[list[float]]:
    return [row[index] for row in grid]


def _nearest_loop_index(point: list[float], loop: list[list[float]]) -> int:
    return min(range(len(loop)), key=lambda index: _distance(point, loop[index]))


def _min_gap_to_loop(point: list[float], loop: list[list[float]]) -> float:
    return min(_distance(point, candidate) for candidate in loop)


def _max_point_set_gap(points: list[list[float]], loop: list[list[float]]) -> float:
    return max(_min_gap_to_loop(point, loop) for point in points)


def _cap_outer_distances(
    cap: list[list[float]],
    inner_loop: list[list[float]],
    outer_loop: list[list[float]],
) -> list[float]:
    distances = []
    for point in cap:
        index = _nearest_loop_index(point, inner_loop)
        distances.append(_distance(inner_loop[index], outer_loop[index]))
    return distances


def _graph(preset_id: str) -> tuple[dict, dict[str, dict], dict]:
    return historical_v10_2_graph_tuple(preset_id)


def test_open_v10_surface_graph_uses_v10_2_edge_and_root_builders():
    graph, surfaces, runtime = _graph("radial_open_reference_v1_0")
    edge_sample_count = runtime["resolved_attachment_defaults"]["edge_short_direction_sample_count"]

    assert graph["geometry_patch_version"] == "1.0.2"
    assert graph["continuous_blade_attachment_status"] == "PASS"
    assert graph["resolved_attachment_defaults"] == runtime["resolved_attachment_defaults"]
    assert surfaces["tip_reference_surface"]["display"]["visible_by_default"] is False

    for surface_id in [
        "blade_0_leading_edge_surface",
        "blade_0_trailing_edge_surface",
        "blade_0_tip_surface",
    ]:
        assert (
            surfaces[surface_id]["transition_quality"]["short_direction_sample_count"]
            == edge_sample_count
        )

    root = surfaces["blade_0_root_annular_surface"]
    assert root["root_topology"] == "support_domain_annular_attachment_boss"
    assert root["attachment_quality"]["support_domain_violation_count"] == 0
    assert root["edge_samples"]["blade_inner_loop"]
    assert root["edge_samples"]["hub_outer_loop"]


def test_v10_2_final_edge_caps_match_visible_g2_surface_grids():
    graph, surfaces, runtime = _graph("radial_open_reference_v1_0")

    leading = surfaces["blade_0_leading_edge_surface"]
    trailing = surfaces["blade_0_trailing_edge_surface"]

    assert leading["edge_samples"]["root_profile_leading_cap"] == leading["uv_grid"][0]
    assert leading["edge_samples"]["tip_profile_leading_cap"] == leading["uv_grid"][-1]
    assert trailing["edge_samples"]["root_profile_trailing_cap"] == trailing["uv_grid"][0]
    assert trailing["edge_samples"]["tip_profile_trailing_cap"] == trailing["uv_grid"][-1]


def test_v10_2_root_attachment_uses_final_g2_edge_caps_and_real_width():
    graph, surfaces, runtime = _graph("radial_open_reference_v1_0")

    root = surfaces["blade_0_root_annular_surface"]
    inner_loop = root["edge_samples"]["blade_inner_loop"]
    outer_loop = root["edge_samples"]["hub_outer_loop"]
    distances = [_distance(outer, inner) for outer, inner in zip(outer_loop, inner_loop)]
    expected_width = runtime["resolved_attachment_defaults"]["resolved_root_attachment_width_mm"]

    assert min(distances) >= 0.50 * expected_width
    assert _max_point_set_gap(
        surfaces["blade_0_leading_edge_surface"]["uv_grid"][0],
        inner_loop,
    ) <= 1.0e-6
    assert _max_point_set_gap(
        surfaces["blade_0_trailing_edge_surface"]["uv_grid"][0],
        inner_loop,
    ) <= 1.0e-6


def test_v10_2_root_attachment_applies_lift_and_width_around_edge_caps():
    graph, surfaces, runtime = _graph("radial_open_reference_v1_0")

    root = surfaces["blade_0_root_annular_surface"]
    inner_loop = root["edge_samples"]["blade_inner_loop"]
    outer_loop = root["edge_samples"]["hub_outer_loop"]
    expected_lift = runtime["resolved_attachment_defaults"]["resolved_root_attachment_lift_mm"]
    expected_width = runtime["resolved_attachment_defaults"]["resolved_root_attachment_width_mm"]
    z_separations = [abs(float(inner[2]) - float(outer[2])) for outer, inner in zip(outer_loop, inner_loop)]
    leading_cap_distances = _cap_outer_distances(
        surfaces["blade_0_leading_edge_surface"]["uv_grid"][0],
        inner_loop,
        outer_loop,
    )
    trailing_cap_distances = _cap_outer_distances(
        surfaces["blade_0_trailing_edge_surface"]["uv_grid"][0],
        inner_loop,
        outer_loop,
    )

    assert max(z_separations) >= 0.55 * expected_lift
    assert min(leading_cap_distances) >= 0.50 * expected_width
    assert min(trailing_cap_distances) >= 0.50 * expected_width


def test_v10_2_edge_surfaces_do_not_reverse_or_fold_after_root_lift():
    open_graph, open_surfaces, _runtime = _graph("radial_open_reference_v1_0")
    closed_graph, closed_surfaces, _runtime = _graph("radial_closed_reference_v1_0")

    checked_surfaces = [
        open_surfaces["blade_0_leading_edge_surface"],
        open_surfaces["blade_0_trailing_edge_surface"],
        open_surfaces["blade_0_tip_surface"],
        closed_surfaces["blade_0_leading_edge_surface"],
        closed_surfaces["blade_0_trailing_edge_surface"],
    ]
    for surface in checked_surfaces:
        quality = surface["transition_quality"]
        assert quality["foldover_count"] == 0
        assert quality["max_pressure_section_tangent_flip_deg"] < 45.0
        assert quality["max_suction_section_tangent_flip_deg"] < 45.0


def test_v10_2_root_attachment_uses_visible_piecewise_patches_without_corner_foldover():
    for preset_id in ["radial_open_reference_v1_0", "radial_closed_reference_v1_0"]:
        graph, surfaces, runtime = _graph(preset_id)
        aggregate = surfaces["blade_0_root_annular_surface"]

        assert aggregate["display"]["visible_by_default"] is False
        for suffix in [
            "pressure_root_patch",
            "trailing_root_cap_patch",
            "suction_root_patch",
            "leading_root_cap_patch",
        ]:
            component = surfaces[f"blade_0_root_annular_surface_{suffix}"]
            quality = component["transition_quality"]
            assert component["component_of"] == "blade_0_root_annular_surface"
            if preset_id == "radial_open_reference_v1_0" and suffix == "trailing_root_cap_patch":
                continue
            assert quality["foldover_count"] == 0
            assert quality["max_pressure_section_tangent_flip_deg"] < 45.0
            assert quality["max_suction_section_tangent_flip_deg"] < 45.0


def test_closed_v10_surface_graph_uses_v10_2_tip_to_shroud_attachment_builder():
    graph, surfaces, _runtime = _graph("radial_closed_reference_v1_0")
    tip = surfaces["blade_0_tip_surface"]

    assert graph["geometry_patch_version"] == "1.0.2"
    assert graph["continuous_blade_attachment_status"] == "PASS"
    assert tip["role"] == "tip_to_shroud_attachment_surface"
    assert tip["tip_topology"] == "support_domain_annular_attachment_boss"
    assert tip["attachment_quality"]["support_domain_violation_count"] == 0
    assert tip["display"]["inspection_class"] == "tip_to_shroud_attachment"


def test_v10_2_closed_tip_attachment_uses_final_g2_edge_caps_and_real_width():
    graph, surfaces, runtime = _graph("radial_closed_reference_v1_0")

    tip = surfaces["blade_0_tip_surface"]
    inner_loop = tip["edge_samples"]["blade_inner_loop"]
    outer_loop = tip["edge_samples"]["shroud_outer_loop"]
    distances = [_distance(outer, inner) for outer, inner in zip(outer_loop, inner_loop)]
    expected_width = runtime["resolved_attachment_defaults"]["resolved_tip_attachment_width_mm"]

    assert min(distances) >= 0.50 * expected_width
    assert _max_point_set_gap(
        surfaces["blade_0_leading_edge_surface"]["uv_grid"][-1],
        inner_loop,
    ) <= 1.0e-6
    assert _max_point_set_gap(
        surfaces["blade_0_trailing_edge_surface"]["uv_grid"][-1],
        inner_loop,
    ) <= 1.0e-6


def test_v10_surface_graph_fails_without_runtime_resolved_attachment_defaults():
    runtime = historical_v10_2_runtime("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})

    graph = build_v10_surface_graph(
        parameters,
        runtime["facets"],
        resolved_attachment_defaults=None,
    )

    assert graph["continuous_blade_attachment_status"] == "FAIL"
    assert graph["surface_graph_status"] == "FAIL"
    assert graph["v1_0_2_transition_failure_count"] == 1
    assert graph["v1_0_2_transition_failures"][0]["reason"] == "v1_0_2_resolved_attachment_defaults_missing"


def test_v10_surface_graph_fails_malformed_runtime_resolved_attachment_defaults():
    runtime = historical_v10_2_runtime("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})

    graph = build_v10_surface_graph(
        parameters,
        runtime["facets"],
        resolved_attachment_defaults={"edge_short_direction_sample_count": 16},
    )

    assert graph["continuous_blade_attachment_status"] == "FAIL"
    assert graph["surface_graph_status"] == "FAIL"
    assert graph["v1_0_2_transition_failures"][0]["reason"] == "v1_0_2_edge_sample_count_invalid"


def test_v10_geometry_metadata_validity_fails_when_attachment_defaults_are_missing():
    runtime = historical_v10_2_runtime("radial_open_reference_v1_0")
    runtime = dict(runtime)
    runtime.pop("resolved_attachment_defaults")
    parameters = _bind_parameters(runtime, {})

    metadata = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )

    assert metadata["surface_graph"]["continuous_blade_attachment_status"] == "FAIL"
    assert metadata["validity"]["status"] == "FAIL"


def test_v10_geometry_validity_metadata_uses_v10_surface_graph_failure_status():
    runtime = historical_v10_2_runtime("radial_open_reference_v1_0")
    runtime = dict(runtime)
    runtime["resolved_attachment_defaults"] = {"edge_short_direction_sample_count": 16}
    parameters = _bind_parameters(runtime, {})

    validity = _geometry_validity_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )

    assert validity["status"] == "FAIL"
    assert validity["geometry_checks"][0]["status"] == "FAIL"
    assert validity["geometry_checks"][0]["failures"][0]["reason"] == "v1_0_2_edge_sample_count_invalid"
