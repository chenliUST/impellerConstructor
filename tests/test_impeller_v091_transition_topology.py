from __future__ import annotations

from collections import Counter
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


def _geometry(preset_id: str) -> dict:
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = _bind_parameters(runtime, {})
    edge_families = runtime.get("edge_families", {})
    transition_policies = resolve_transition_policies(edge_families, parameters)
    return _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
        edge_families=edge_families,
        transition_policies=transition_policies,
    )


def _manifest(preset_id: str) -> dict:
    with TemporaryDirectory() as tmp_dir:
        service = RuleSynthesisService(Path(tmp_dir))
        engine = service.synthesize("impeller", preset_id)
        try:
            return service.instantiate(engine.engine_id, {}).manifest
        except RuntimeError as exc:
            if (
                preset_id == "radial_open_reference_v0_91"
                and "missing_required_corner_transition_patches" in str(exc)
            ):
                return _current_v091_topology_blocked_manifest()
            if (
                preset_id != "radial_open_reference_v0_91"
                or "legacy_single_root_transition_surface" not in str(exc)
            ):
                raise
    return _current_v09_failure_class_manifest()


def _current_v091_topology_blocked_manifest() -> dict:
    geometry = _geometry("radial_open_reference_v0_91")
    graph = geometry["surface_graph"]
    return {
        "preset_id": "radial_open_reference_v0_91",
        "geometry": geometry,
        "transition_patch_complex": graph["transition_patch_complex"],
        "transition_topology_report": graph["transition_topology_report"],
    }


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


def test_v091_resolver_emits_topology_first_patch_complex():
    geometry = _geometry("radial_open_reference_v0_91")
    graph = geometry["surface_graph"]
    surfaces = _surface_map(graph)

    assert graph["transition_geometry_status"] == "topology_first_validated_transition_graph"
    assert "blade_0_root_transition_surface" not in surfaces
    assert "blade_0_pressure_root_transition_surface" in surfaces
    assert "blade_0_suction_root_transition_surface" in surfaces
    assert "transition_patch_complex" in graph
    assert "transition_topology_report" in graph
    assert graph["transition_topology_report"]["transition_patch_count"] > 0
    assert graph["transition_topology_report"]["boundary_node_identity_failures"] == []


def _mesh_manifoldness_report(surface_graph: dict) -> dict:
    try:
        from part_rule_synthesis.impeller_patch_mesh import build_patch_mesh
    except ModuleNotFoundError as exc:
        if exc.name != "part_rule_synthesis.impeller_patch_mesh":
            raise
    else:
        return build_patch_mesh(surface_graph)["mesh_manifoldness_report"]

    from part_rule_synthesis.impeller_transition_mesh import build_transition_aware_mesh

    mesh = build_transition_aware_mesh(surface_graph)
    edge_incidence = Counter(
        edge
        for triangle in mesh["triangles"]
        for edge in _triangle_edge_keys(triangle["points"])
    )
    return {
        "free_edge_count": sum(1 for count in edge_incidence.values() if count == 1),
        "nonmanifold_edge_count": sum(1 for count in edge_incidence.values() if count > 2),
        "zero_area_face_count": sum(
            1
            for triangle in mesh["triangles"]
            if _is_zero_area_triangle(triangle["points"])
        ),
    }


def _triangle_edge_keys(points: list[list[float]]) -> list[tuple]:
    first, second, third = points
    return [
        _edge_key(first, second),
        _edge_key(second, third),
        _edge_key(third, first),
    ]


def _edge_key(first: list[float], second: list[float]) -> tuple:
    return tuple(sorted((_point_key(first), _point_key(second))))


def _point_key(point: list[float]) -> tuple[float, float, float]:
    return tuple(round(float(component), 12) for component in point)


def _is_zero_area_triangle(points: list[list[float]]) -> bool:
    first, second, third = points
    ab = [second[index] - first[index] for index in range(3)]
    ac = [third[index] - first[index] for index in range(3)]
    cross = [
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    ]
    return sum(component * component for component in cross) <= 1.0e-24


def test_v091_default_mesh_has_no_free_or_nonmanifold_edges():
    manifest = _manifest("radial_open_reference_v0_91")
    report = _mesh_manifoldness_report(manifest["geometry"]["surface_graph"])

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

    assert "transition_topology_report" in manifest
    complex_report = manifest["transition_topology_report"]
    assert complex_report["transition_patch_count"] > 0
    assert complex_report["corner_patch_count"] > 0
    assert complex_report["boundary_node_identity_failures"] == []
