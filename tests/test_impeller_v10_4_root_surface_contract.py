from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v10_3_blade_faces import build_blade_faces_from_section_lattice
from part_rule_synthesis.impeller_v10_3_root_blend import build_v10_3_root_blend
from part_rule_synthesis.impeller_v10_3_section_loop import build_section_loop_lattice
from part_rule_synthesis.impeller_v10_4_root_surface import _reason, build_v10_4_root_surface
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata
from part_rule_synthesis.impeller_v10_surface_graph import (
    _v10_3_hub_support_surface,
    _v10_3_nurbs_carrier_geometry,
)


def _graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )["surface_graph"]

def _surface(graph: dict, surface_id: str) -> dict:
    return next(surface for surface in graph["surfaces"] if surface["id"] == surface_id)


def _root_components(graph: dict) -> list[dict]:
    return [
        surface
        for surface in graph["surfaces"]
        if surface.get("component_of") == "blade_0_root_annular_surface"
    ]


def _direct_roots() -> tuple[dict, dict]:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    defaults = runtime["resolved_section_loop_defaults"]
    carrier_geometry = _v10_3_nurbs_carrier_geometry(
        parameters=parameters,
        facets=runtime["facets"],
        profile_defaults=runtime.get("profile_defaults"),
        resolved_section_loop_defaults=defaults,
    )
    lattice = build_section_loop_lattice(
        parameters=parameters,
        defaults=defaults,
        carrier_geometry=carrier_geometry,
    )
    assert lattice["status"] == "PASS"
    faces = build_blade_faces_from_section_lattice(lattice)
    assert faces["status"] == "PASS"
    hub_surface = _v10_3_hub_support_surface(
        parameters,
        defaults,
        carrier_geometry=carrier_geometry,
    )
    root_v10_3 = build_v10_3_root_blend(
        blade_index=0,
        lattice=lattice,
        blade_faces=faces["surfaces"],
        hub_surface=hub_surface,
        defaults=defaults,
    )
    root_v10_4 = build_v10_4_root_surface(
        blade_index=0,
        lattice=lattice,
        blade_faces=faces["surfaces"],
        hub_surface=hub_surface,
        defaults=defaults,
    )
    return root_v10_3, root_v10_4


def _distance_2d(left: list[float], right: list[float]) -> float:
    return math.hypot(float(left[0]) - float(right[0]), float(left[1]) - float(right[1]))


def _hub_radius_at_z(hub_surface: dict, z_value: float) -> float:
    profile = sorted(
        [
            (
                float(sample.get("radius_mm", sample.get("r_mm"))),
                float(sample["z_mm"]),
            )
            for sample in hub_surface["profile_samples_rz"]
        ],
        key=lambda sample: sample[1],
    )
    if z_value <= profile[0][1]:
        return profile[0][0]
    if z_value >= profile[-1][1]:
        return profile[-1][0]
    for (left_radius, left_z), (right_radius, right_z) in zip(profile, profile[1:]):
        if left_z <= z_value <= right_z:
            t = (z_value - left_z) / (right_z - left_z)
            return left_radius * (1.0 - t) + right_radius * t
    raise AssertionError(f"z outside hub profile: {z_value}")


def _signed_height_to_hub(point: list[float], hub_surface: dict) -> float:
    radius = math.hypot(float(point[0]), float(point[1]))
    return radius - _hub_radius_at_z(hub_surface, float(point[2]))


def test_v10_4_root_builder_has_no_v10_3_root_blend_dependency(monkeypatch) -> None:
    source = (SRC_ROOT / "part_rule_synthesis" / "impeller_v10_4_root_surface.py").read_text(
        encoding="utf-8"
    )

    assert "impeller_v10_3_root_blend" not in source
    assert "build_v10_3_root_blend" not in source

    import part_rule_synthesis.impeller_v10_3_root_blend as v10_3_root_blend
    import part_rule_synthesis.impeller_v10_4_root_surface as v10_4_root_surface

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("V1.0.4 root surface must not call V1.0.3 root blend")

    monkeypatch.setattr(v10_3_root_blend, "build_v10_3_root_blend", fail_if_called)
    monkeypatch.setattr(v10_4_root_surface, "build_v10_3_root_blend", fail_if_called, raising=False)

    graph = _graph()
    quality = _surface(graph, "blade_0_root_annular_surface")["v1_0_4_root_quality"]

    assert graph["geometry_patch_version"] == "1.0.4"
    assert quality["status"] == "PASS"


def test_v10_4_root_components_have_consistent_material_side_and_no_foldover() -> None:
    graph = _graph()
    components = _root_components(graph)

    assert {component["id"] for component in components} == {
        "blade_0_root_annular_surface_pressure_root_patch",
        "blade_0_root_annular_surface_leading_root_cap_patch",
        "blade_0_root_annular_surface_suction_root_patch",
        "blade_0_root_annular_surface_trailing_root_cap_patch",
    }
    assert {component["component_segment"] for component in components} == {
        "pressure_side",
        "leading_edge",
        "suction_side",
        "trailing_edge",
    }
    for component in components:
        quality = component["v1_0_4_root_quality"]
        assert quality["root_patch_orientation_status"] == "PASS"
        assert quality["material_side_status"] == "PASS"
        assert quality["foldover_count"] == 0
        assert "max_parameter_direction_flip_deg" in quality
        assert quality["max_parameter_direction_flip_role"] == "diagnostic_only"


def test_v10_4_root_surface_rebuilds_geometry_instead_of_relabeling_v10_3_root_blend() -> None:
    root_v10_3, root_v10_4 = _direct_roots()

    assert root_v10_3["status"] == "PASS"
    assert root_v10_4["status"] == "PASS"
    assert root_v10_4["edge_samples"]["blade_inner_loop"] == root_v10_3["edge_samples"]["blade_inner_loop"]
    assert root_v10_4["uv_grid"] != root_v10_3["uv_grid"]


def test_v10_4_root_quality_reason_blocks_orientation_failure_with_width_samples() -> None:
    reason = _reason(
        orientation="FAIL",
        material="PASS",
        widths=[10.0, 10.0],
        lifts=[10.0, 10.0],
        target_width=10.0,
        target_lift=10.0,
    )

    assert reason == "v1_0_4_root_foldover"


def test_v10_4_root_quality_reason_blocks_lift_outside_target_band() -> None:
    reason = _reason(
        orientation="PASS",
        material="PASS",
        widths=[10.0, 10.0],
        lifts=[7.9, 10.0],
        target_width=10.0,
        target_lift=10.0,
    )

    assert reason == "v1_0_4_root_lift_nonuniform"


def test_v10_4_root_width_and_lift_match_half_blade_thickness_contract() -> None:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    contract = runtime["v1_0_4_preset_contract"]
    expected_width = contract["expected_root_width_mm"]
    expected_lift = contract["expected_root_lift_mm"]
    width_tolerance = expected_width * contract["root_width_variation_limit_fraction"]
    lift_tolerance = expected_lift * contract["root_lift_variation_limit_fraction"]
    graph = _graph()
    hub_surface = _surface(graph, "hub_support_surface")
    aggregate = _surface(graph, "blade_0_root_annular_surface")
    quality = aggregate["v1_0_4_root_quality"]

    assert quality["target_root_width_mm"] == expected_width
    assert quality["target_root_lift_mm"] == expected_lift
    assert expected_width - width_tolerance <= quality["min_root_width_mm"] <= expected_width + width_tolerance
    assert expected_width - width_tolerance <= quality["max_root_width_mm"] <= expected_width + width_tolerance
    assert expected_lift - lift_tolerance <= quality["min_root_lift_mm"] <= expected_lift + lift_tolerance
    assert expected_lift - lift_tolerance <= quality["max_root_lift_mm"] <= expected_lift + lift_tolerance

    components = _root_components(graph)
    measured_widths = []
    measured_lifts = []
    for component in components:
        support_domain = component["v1_0_4_root_quality"]["support_domain_width_samples_mm"]
        measured_widths.extend(support_domain)
        measured_lifts.extend(
            _signed_height_to_hub(point, hub_surface)
            for point in component["edge_samples"]["blade_inner_loop"]
        )

    assert quality["min_root_width_mm"] == min(round(value, 6) for value in measured_widths)
    assert quality["max_root_width_mm"] == max(round(value, 6) for value in measured_widths)
    assert quality["min_root_lift_mm"] == round(min(measured_lifts), 6)
    assert quality["max_root_lift_mm"] == round(max(measured_lifts), 6)
