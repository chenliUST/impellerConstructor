from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.api import create_app
import part_rule_synthesis.service as service_module
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_4_engineering_drawing import (
    build_engineering_drawing_contract,
    validate_engineering_drawing_contract,
)
from part_rule_synthesis.impeller_v11_surface_family import build_v11_surface_graph


ACTIVE_PRESETS = [
    "radial_open_reference_v1_1",
    "radial_closed_reference_v1_1",
    "nasa_stage37_stator_ring_v1_1",
    "rr_ultrafan_cti_fan_v1_1",
    "public_rocket_turbopump_inducer_v1_1",
]


def graph_for(preset_id: str = ACTIVE_PRESETS[0]) -> dict:
    runtime = compile_impeller_runtime_preset(preset_id)
    parameters = {name: spec["default"] for name, spec in runtime["parameters"].items()}
    defaults = {
        **runtime["resolved_blade_to_blade_loop_family_defaults"],
        "canonical_nurbs_parameterization": runtime["canonical_nurbs_parameterization"],
    }
    return build_v11_surface_graph(parameters, runtime["facets"], defaults)


def test_contract_is_semantic_and_has_three_authoritative_span_sections():
    graph = graph_for()
    contract = build_engineering_drawing_contract(graph, preset_id=ACTIVE_PRESETS[0])

    assert contract["contract_version"] == "1.1.4"
    assert contract["generation_id"] == graph["generation_id"]
    assert contract["units"] == "mm"
    assert [section["station_role"] for section in contract["views"]["top"]["cross_sections"]] == [
        "active_root",
        "midspan",
        "active_tip",
    ]
    assert contract["views"]["top"]["outline_paths"]
    assert contract["views"]["meridional"]["profiles"]
    assert contract["views"]["meridional"]["control_polygons"]
    meridional_dimension_ids = [item["id"] for item in contract["views"]["meridional"]["dimensions"]]
    assert len(meridional_dimension_ids) == len(set(meridional_dimension_ids))
    assert len([item for item in meridional_dimension_ids if "attachment:root:" in item]) == 2
    assert contract["views"]["s_q"]["blade_rows"][0]["blade_class"] == "main"
    assert contract["views"]["s_q"]["blade_rows"][1]["blade_class"] == "splitter"
    assert validate_engineering_drawing_contract(graph, contract) == []


def test_every_measured_dimension_has_geometry_witnesses_not_viewport_coordinates():
    contract = build_engineering_drawing_contract(graph_for(), preset_id=ACTIVE_PRESETS[0])

    dimensions = [
        dimension
        for view in contract["views"].values()
        for dimension in view.get("dimensions", [])
        if dimension["kind"] != "note"
    ]
    dimensions += [
        dimension
        for section in contract["views"]["top"]["cross_sections"]
        for dimension in section["dimensions"]
        if dimension["kind"] != "note"
    ]
    dimensions += [
        dimension
        for row in contract["views"]["s_q"]["blade_rows"]
        for dimension in row["dimensions"]
        if dimension["kind"] != "note"
    ]

    assert dimensions
    assert all(len(dimension["witness_points"]) >= 2 for dimension in dimensions)
    assert all(dimension["source_feature_ids"] for dimension in dimensions)
    assert all("viewport" not in dimension for dimension in dimensions)


def test_zero_splitter_presets_have_one_s_q_row():
    for preset_id in ACTIVE_PRESETS[1:]:
        contract = build_engineering_drawing_contract(graph_for(preset_id), preset_id=preset_id)
        assert [row["blade_class"] for row in contract["views"]["s_q"]["blade_rows"]] == ["main"]


def test_all_active_presets_instantiate_with_empty_parameters_and_expose_lazy_drawing(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(service_module, "_write_exports", lambda *args, **kwargs: ({}, {}))
    monkeypatch.setattr(service_module, "_geometry_kernel_metadata", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        service_module,
        "_geometry_validity_metadata",
        lambda *args, **kwargs: {"status": "PASS", "geometry_checks": [], "topology_checks": []},
    )
    monkeypatch.setattr(service_module, "build_surface_mesh_manifest", lambda *args, **kwargs: {})
    client = TestClient(create_app(tmp_path))

    for preset_id in ACTIVE_PRESETS:
        engine_response = client.post(
            "/api/rule-engines/synthesize",
            json={"part_family_id": "impeller", "preset_id": preset_id},
        )
        assert engine_response.status_code == 200, preset_id
        run_response = client.post(
            f"/api/rule-engines/{engine_response.json()['engine_id']}/instantiate",
            json={"parameters": {}, "geometry_stage": "edge_closures"},
        )
        assert run_response.status_code == 200, (preset_id, run_response.text)
        manifest = run_response.json()["manifest"]
        drawing_response = client.get(
            f"/api/model-runs/{manifest['run_id']}/engineering-drawing"
        )
        assert drawing_response.status_code == 200, preset_id
        assert drawing_response.json()["preset_id"] == preset_id


def test_population_error_reports_preset_and_expected_composition(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_closed_reference_v1_1"},
    ).json()

    response = client.post(
        f"/api/rule-engines/{engine['engine_id']}/instantiate",
        json={"parameters": {"blade_count": 16}},
    )

    assert response.status_code == 400
    assert "radial_closed_reference_v1_1" in response.json()["detail"]
    assert "received blade_count=16" in response.json()["detail"]
    assert "main_blade_count=12" in response.json()["detail"]
    assert "splitter_blade_count=0" in response.json()["detail"]
