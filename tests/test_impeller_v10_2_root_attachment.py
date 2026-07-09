from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from impeller_v10_2_historical_fixture import historical_v10_2_graph_tuple
from part_rule_synthesis.impeller_v10_2_blade_lattice import build_v10_2_blade_lattice
from part_rule_synthesis.impeller_v10_2_support_attachment import (
    build_v10_2_root_attachment_surface,
)


_MISSING = object()


def _open_runtime_surfaces_and_lattice() -> tuple[dict, dict[str, dict], dict]:
    _graph, surfaces, runtime = historical_v10_2_graph_tuple("radial_open_reference_v1_0")
    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)
    return runtime, surfaces, lattice


def _defaults_with(**overrides):
    runtime, surfaces, lattice = _open_runtime_surfaces_and_lattice()
    defaults = dict(runtime["resolved_attachment_defaults"])
    for key, value in overrides.items():
        if value is _MISSING:
            defaults.pop(key, None)
        else:
            defaults[key] = value
    return surfaces, lattice, defaults


def test_root_attachment_builds_review_grade_annular_surface_from_real_open_lattice():
    runtime, surfaces, lattice = _open_runtime_surfaces_and_lattice()

    root = build_v10_2_root_attachment_surface(
        blade_index=0,
        lattice=lattice,
        hub_surface=surfaces["hub_revolve_surface"],
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert lattice["status"] == "PASS"
    assert root["role"] == "root_pedestal_ring_surface"
    assert root["root_topology"] == "support_domain_annular_attachment_boss"
    assert root["edge_samples"]["blade_inner_loop"] == lattice["closed_loops"]["blade_exterior_root_loop"]
    assert root["edge_samples"]["blade_inner_loop"] is not lattice["closed_loops"]["blade_exterior_root_loop"]
    assert root["attachment_quality"]["inner_loop_max_gap_to_blade_faces_mm"] == 0.0
    assert root["attachment_quality"]["outer_loop_max_gap_to_hub_surface_mm"] <= 1.0e-6
    assert root["attachment_quality"]["root_attachment_width_mm"] > 0.0
    assert root["attachment_quality"]["root_attachment_lift_mm"] > 0.0
    assert root["attachment_quality"]["foldover_count"] == 0
    assert root["attachment_quality"]["support_domain_collapse_count"] == 0
    assert (
        root["attachment_quality"]["g2_builder_global_reference_foldover_count"]
        == root["transition_quality"]["foldover_count"]
    )


def test_root_attachment_deep_copies_blade_inner_loop_on_success_and_failure():
    runtime, surfaces, lattice = _open_runtime_surfaces_and_lattice()
    lattice_loop = lattice["closed_loops"]["blade_exterior_root_loop"]
    original_first_point = list(lattice_loop[0])

    success = build_v10_2_root_attachment_surface(
        blade_index=0,
        lattice=lattice,
        hub_surface=surfaces["hub_revolve_surface"],
        defaults=runtime["resolved_attachment_defaults"],
    )
    failure = build_v10_2_root_attachment_surface(
        blade_index=0,
        lattice=lattice,
        hub_surface={"id": "missing_profile_support"},
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert success["edge_samples"]["blade_inner_loop"] == lattice_loop
    assert failure["edge_samples"]["blade_inner_loop"] == lattice_loop
    assert success["edge_samples"]["blade_inner_loop"] is not lattice_loop
    assert failure["edge_samples"]["blade_inner_loop"] is not lattice_loop
    assert success["edge_samples"]["blade_inner_loop"][0] is not lattice_loop[0]
    assert failure["edge_samples"]["blade_inner_loop"][0] is not lattice_loop[0]

    success["edge_samples"]["blade_inner_loop"][0][0] += 123.0
    failure["edge_samples"]["blade_inner_loop"][0][1] += 456.0

    assert lattice["closed_loops"]["blade_exterior_root_loop"][0] == original_first_point


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"resolved_root_attachment_width_mm": _MISSING}, "v1_0_2_root_attachment_width_invalid"),
        ({"resolved_root_attachment_width_mm": 0.0}, "v1_0_2_root_attachment_width_invalid"),
        ({"resolved_root_attachment_lift_mm": _MISSING}, "v1_0_2_root_attachment_lift_invalid"),
        ({"resolved_root_attachment_lift_mm": 0.0}, "v1_0_2_root_attachment_lift_invalid"),
        ({"attachment_short_direction_sample_count": 16}, "v1_0_2_root_attachment_sample_count_invalid"),
        ({"attachment_short_direction_sample_count": 17.0}, "v1_0_2_root_attachment_sample_count_invalid"),
    ],
)
def test_root_attachment_reports_invalid_defaults_as_failure_surface(overrides, reason):
    surfaces, lattice, defaults = _defaults_with(**overrides)

    root = build_v10_2_root_attachment_surface(
        blade_index=0,
        lattice=lattice,
        hub_surface=surfaces["hub_revolve_surface"],
        defaults=defaults,
    )

    assert root["attachment_quality"]["status"] == "FAIL"
    assert root["attachment_quality"]["reason"] == reason
    assert root["uv_grid"] == []


def test_root_attachment_uses_runtime_short_direction_sample_count_and_visibility_metadata():
    runtime, surfaces, lattice = _open_runtime_surfaces_and_lattice()

    root = build_v10_2_root_attachment_surface(
        blade_index=0,
        lattice=lattice,
        hub_surface=surfaces["hub_revolve_surface"],
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert len(root["uv_grid"][0]) == runtime["resolved_attachment_defaults"]["attachment_short_direction_sample_count"]
    assert (
        root["transition_quality"]["short_direction_sample_count"]
        == runtime["resolved_attachment_defaults"]["attachment_short_direction_sample_count"]
    )
    assert root["display"]["inspection_class"] == "root_to_hub_native_root_face"
    assert root["display"]["color"] == "#ff00cc"
    assert root["display"]["wire_color"] == "#fff200"


def test_root_attachment_failure_path_reports_projection_failure_status():
    runtime, _surfaces, lattice = _open_runtime_surfaces_and_lattice()

    root = build_v10_2_root_attachment_surface(
        blade_index=0,
        lattice=lattice,
        hub_surface={"id": "missing_profile_support"},
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert root["role"] == "root_pedestal_ring_surface"
    assert root["attachment_quality"]["status"] == "FAIL"
    assert root["attachment_quality"]["reason"] == "v1_0_2_support_profile_samples_missing"
