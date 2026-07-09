from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis import service
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v10_2_blade_lattice import build_v10_2_blade_lattice
from part_rule_synthesis.impeller_v10_2_support_attachment import (
    build_v10_2_tip_attachment_surface,
)


_MISSING = object()


def _closed_runtime_surfaces_and_lattice() -> tuple[dict, dict[str, dict], dict]:
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_0")
    parameters = service._bind_parameters(runtime, {})
    metadata = service._geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )
    surfaces = {surface["id"]: surface for surface in metadata["surface_graph"]["surfaces"]}
    lattice = build_v10_2_blade_lattice(blade_index=0, surfaces=surfaces)
    return runtime, surfaces, lattice


def _defaults_with(**overrides):
    runtime, surfaces, lattice = _closed_runtime_surfaces_and_lattice()
    defaults = dict(runtime["resolved_attachment_defaults"])
    for key, value in overrides.items():
        if value is _MISSING:
            defaults.pop(key, None)
        else:
            defaults[key] = value
    return surfaces, lattice, defaults


def test_tip_attachment_builds_closed_review_grade_annular_surface_from_real_lattice():
    runtime, surfaces, lattice = _closed_runtime_surfaces_and_lattice()

    tip = build_v10_2_tip_attachment_surface(
        blade_index=0,
        lattice=lattice,
        shroud_surface=surfaces["shroud_surface"],
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert lattice["status"] == "PASS"
    assert tip["id"] == "blade_0_tip_surface"
    assert tip["role"] == "tip_to_shroud_attachment_surface"
    assert tip["tip_topology"] == "support_domain_annular_attachment_boss"
    assert tip["edge_samples"]["blade_inner_loop"] == lattice["closed_loops"]["blade_exterior_tip_loop"]
    assert tip["edge_samples"]["blade_inner_loop"] is not lattice["closed_loops"]["blade_exterior_tip_loop"]
    assert tip["edge_samples"]["blade_inner_loop"][0] is not lattice["closed_loops"]["blade_exterior_tip_loop"][0]
    assert tip["attachment_quality"]["outer_loop_max_gap_to_shroud_surface_mm"] <= 1.0e-6
    assert tip["attachment_quality"]["foldover_count"] == 0
    assert tip["attachment_quality"]["support_domain_violation_count"] == 0
    assert (
        tip["attachment_quality"]["g2_builder_global_reference_foldover_count"]
        == tip["transition_quality"]["foldover_count"]
    )


def test_tip_attachment_uses_runtime_short_direction_sample_count_and_visibility_metadata():
    runtime, surfaces, lattice = _closed_runtime_surfaces_and_lattice()

    tip = build_v10_2_tip_attachment_surface(
        blade_index=0,
        lattice=lattice,
        shroud_surface=surfaces["shroud_surface"],
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert len(tip["uv_grid"][0]) == runtime["resolved_attachment_defaults"]["attachment_short_direction_sample_count"]
    assert (
        tip["transition_quality"]["short_direction_sample_count"]
        == runtime["resolved_attachment_defaults"]["attachment_short_direction_sample_count"]
    )
    assert tip["display"]["inspection_class"] == "tip_to_shroud_attachment"
    assert tip["display"]["color"] == "#00e5ff"
    assert tip["display"]["wire_color"] == "#fff200"


def test_tip_attachment_failure_path_reports_projection_failure_status():
    runtime, _surfaces, lattice = _closed_runtime_surfaces_and_lattice()

    tip = build_v10_2_tip_attachment_surface(
        blade_index=0,
        lattice=lattice,
        shroud_surface={"id": "missing_profile_support"},
        defaults=runtime["resolved_attachment_defaults"],
    )

    assert tip["role"] == "tip_to_shroud_attachment_surface"
    assert tip["attachment_quality"]["status"] == "FAIL"
    assert tip["attachment_quality"]["reason"] == "v1_0_2_support_profile_samples_missing"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"resolved_tip_attachment_width_mm": _MISSING}, "v1_0_2_tip_attachment_width_invalid"),
        ({"resolved_tip_attachment_width_mm": 0.0}, "v1_0_2_tip_attachment_width_invalid"),
        ({"resolved_tip_attachment_lift_mm": _MISSING}, "v1_0_2_tip_attachment_lift_invalid"),
        ({"resolved_tip_attachment_lift_mm": 0.0}, "v1_0_2_tip_attachment_lift_invalid"),
        ({"attachment_short_direction_sample_count": 16}, "v1_0_2_tip_attachment_sample_count_invalid"),
        ({"attachment_short_direction_sample_count": 17.0}, "v1_0_2_tip_attachment_sample_count_invalid"),
    ],
)
def test_tip_attachment_reports_invalid_defaults_as_failure_surface(overrides, reason):
    surfaces, lattice, defaults = _defaults_with(**overrides)

    tip = build_v10_2_tip_attachment_surface(
        blade_index=0,
        lattice=lattice,
        shroud_surface=surfaces["shroud_surface"],
        defaults=defaults,
    )

    assert tip["attachment_quality"]["status"] == "FAIL"
    assert tip["attachment_quality"]["reason"] == reason
    assert tip["uv_grid"] == []
