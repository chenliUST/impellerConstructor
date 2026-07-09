from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


@lru_cache(maxsize=1)
def _graph() -> dict:
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_0")
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )["surface_graph"]


def test_v10_4_hub_is_concave_and_not_conical_fallback() -> None:
    graph = _graph()
    quality = graph["v1_0_4_hub_quality"]

    assert quality["status"] == "PASS"
    assert quality["hub_profile_concavity_status"] == "PASS"
    assert quality["max_linear_fit_residual_mm"] >= 12.0
    assert quality["hub_profile_conical_fallback"] is False


def test_v10_4_hub_material_and_mounting_bore_faces_exist() -> None:
    graph = _graph()
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}

    for surface_id in [
        "hub_main_revolve_surface",
        "hub_top_cap_surface",
        "hub_bottom_cap_surface",
        "mounting_bore_inner_wall_surface",
        "mounting_bore_top_edge_surface",
        "mounting_bore_bottom_edge_surface",
    ]:
        assert surface_id in surfaces
        surface = surfaces[surface_id]
        assert surface["geometry_patch_version"] == "1.0.4"
        assert surface["wireframe"]["enabled"] is True
        assert surface["uv_grid"]
        assert surface["mesh"]["quad_count"] > 0
        assert surface["display"]["visible_by_default"] is True

    bore = surfaces["mounting_bore_inner_wall_surface"]
    assert bore["v1_0_4_bore_quality"]["status"] == "PASS"
    assert bore["v1_0_4_bore_quality"]["radius_mm"] == 40.0


def test_v10_4_hub_main_reuses_carrier_profile_samples() -> None:
    graph = _graph()
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    hub = surfaces["hub_main_revolve_surface"]

    assert hub["kind"] == "native_topology_face"
    assert hub["source"]["geometry_rule"] == "v1_0_3_hub_support_from_nurbs_carrier_profile"
    assert len(hub["profile_samples_rz"]) >= 20
    assert hub["profile_samples_rz"] == hub["support_profile_samples_rz"]
    assert hub["edge_samples"]["bottom"]
    assert hub["edge_samples"]["top"]
    assert "cone" not in str(hub).lower()


def test_v10_4_hub_does_not_publish_outer_hub_chamfers_by_default() -> None:
    graph = _graph()
    surface_ids = {surface["id"] for surface in graph["surfaces"]}

    assert "hub_chamfer_top_cap_surface" not in surface_ids
    assert "hub_chamfer_bottom_outer_surface" not in surface_ids
