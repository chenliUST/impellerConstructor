from __future__ import annotations

import sys
from math import dist
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_transition_policies import resolve_transition_policies
from part_rule_synthesis.service import (
    RuleSynthesisService,
    _bind_parameters,
    _geometry_metadata,
)


def _manifest(preset_id: str) -> dict:
    with TemporaryDirectory() as tmp_dir:
        service = RuleSynthesisService(Path(tmp_dir))
        engine = service.synthesize("impeller", preset_id)
        try:
            return service.instantiate(engine.engine_id, {}).manifest
        except RuntimeError as exc:
            if (
                preset_id != "radial_open_reference_v0_91"
                or "legacy_single_root_transition_surface" not in str(exc)
            ):
                raise
    return _current_v09_failure_class_manifest()


def _current_v09_failure_class_manifest() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_9")
    parameters = _bind_parameters(runtime, {})
    edge_families = runtime.get("edge_families", {})
    transition_policies = resolve_transition_policies(edge_families, parameters)
    geometry = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
        edge_families=edge_families,
        transition_policies=transition_policies,
    )
    return {
        "preset_id": "radial_open_reference_v0_91",
        "geometry": geometry,
    }


def _surface_map(surface_graph: dict) -> dict:
    return {surface["id"]: surface for surface in surface_graph["surfaces"]}


def test_v091_default_mesh_has_no_free_or_nonmanifold_edges():
    from part_rule_synthesis.impeller_patch_mesh import build_patch_mesh

    manifest = _manifest("radial_open_reference_v0_91")
    mesh = build_patch_mesh(manifest["geometry"]["surface_graph"])

    report = mesh["mesh_manifoldness_report"]
    assert report["free_edge_count"] == 0
    assert report["nonmanifold_edge_count"] == 0
    assert report["zero_area_face_count"] == 0


def test_v091_root_leading_corner_boundaries_are_closed():
    manifest = _manifest("radial_open_reference_v0_91")
    surfaces = _surface_map(manifest["geometry"]["surface_graph"])

    leading = surfaces["blade_0_leading_transition_surface"]["uv_grid"]
    pressure_root = surfaces["blade_0_pressure_root_transition_surface"]["uv_grid"]
    suction_root = surfaces["blade_0_suction_root_transition_surface"]["uv_grid"]

    pressure_gap = dist(leading[0][0], pressure_root[0][0])
    suction_gap = dist(leading[0][-1], suction_root[0][0])

    assert pressure_gap <= 1.0e-5
    assert suction_gap <= 1.0e-5


def test_v091_transition_patch_complex_uses_shared_node_ids():
    manifest = _manifest("radial_open_reference_v0_91")
    complex_report = manifest.get("transition_topology_report", {})

    assert complex_report.get("transition_patch_count", 0) > 0
    assert complex_report.get("corner_patch_count", 0) > 0
    assert complex_report.get("boundary_node_identity_failures") == []
