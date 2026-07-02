import copy
from pathlib import Path

import pytest

from part_rule_synthesis import impeller_dsl_resources as dsl_resources
from part_rule_synthesis import service as service_module
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v07_bundle_loads_schema_and_transition_resources():
    bundle = load_impeller_dsl_bundle("v0_7")

    assert bundle.schema["dsl_version"] == "0.7"
    assert bundle.shape_controls["shape_control_version"] == "0.7"
    assert set(bundle.presets) == {
        "radial_open_reference_v0_7",
        "radial_closed_reference_v0_7",
    }
    assert bundle.export_contracts["surface_graph_bounded_brep"]["mode"] == "surface_graph_bounded_brep"
    assert bundle.export_contracts["surface_graph_bounded_brep"]["step_exactness"] == "surface_graph_mesh_step"
    assert (
        bundle.export_contracts["surface_graph_bounded_brep"]["target_step_exactness"]
        == "surface_graph_trimmed_brep_step"
    )
    assert (
        bundle.export_contracts["surface_graph_bounded_brep"]["diagnostic_step_exactness"]
        == "surface_graph_bounded_unsewn_brep_step"
    )
    assert (
        bundle.export_contracts["surface_graph_bounded_brep"]["bounded_brep_status"]
        == "deferred_until_bounded_face_export"
    )


def test_v07_runtime_exposes_edge_families_and_default_policies():
    bundle = load_impeller_dsl_bundle("v0_7")
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_7")
    preset = bundle.presets["radial_open_reference_v0_7"]
    constructor = bundle.constructors[preset["constructor_id"]]

    assert runtime["version"] == "0.7.0"
    assert runtime["dsl_sections"]["dsl_version"] == "0.7"
    assert "edge_families" in runtime
    assert "transition_policy_defaults" in runtime
    assert runtime["transition_policy_defaults"]["blade_root_to_hub.default"]["treatment"] == "fillet"
    assert runtime["transition_policy_defaults"]["hub_top_outer.default"]["treatment"] == "fillet"

    for edge_family_id, edge_family in constructor["edge_families"].items():
        policy = runtime["transition_policy_defaults"][f"{edge_family_id}.default"]
        radius_parameter = edge_family["default_radius_parameter"]
        assert policy["edge_family"] == edge_family_id
        assert policy["treatment"] == edge_family["default_treatment"]
        assert policy["maps_to_parameters"] == [radius_parameter]
        assert policy["radius_mm"] == float(preset["parameter_values"][radius_parameter])


def test_pre_v07_runtime_does_not_emit_transition_policy_fields():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_6")

    assert "edge_families" not in runtime
    assert "transition_policy_defaults" not in runtime


def test_v07_validation_requires_constructor_edge_families():
    bundle = copy.deepcopy(load_impeller_dsl_bundle("v0_7"))
    constructor_id = bundle.presets["radial_open_reference_v0_7"]["constructor_id"]
    del bundle.constructors[constructor_id]["edge_families"]

    with pytest.raises(ValueError, match=f"constructor {constructor_id} missing required V0.7 edge_families"):
        dsl_resources._validate_bundle(bundle)


@pytest.mark.parametrize("field_name", ["default_treatment", "default_radius_parameter"])
def test_v07_validation_requires_edge_family_default_fields(field_name):
    bundle = copy.deepcopy(load_impeller_dsl_bundle("v0_7"))
    constructor_id = bundle.presets["radial_open_reference_v0_7"]["constructor_id"]
    del bundle.constructors[constructor_id]["edge_families"]["blade_root_to_hub"][field_name]

    with pytest.raises(
        ValueError,
        match=f"constructor {constructor_id} edge family blade_root_to_hub missing {field_name}",
    ):
        dsl_resources._validate_bundle(bundle)


def test_v07_validation_rejects_unsupported_edge_family_default_treatment():
    bundle = copy.deepcopy(load_impeller_dsl_bundle("v0_7"))
    constructor_id = bundle.presets["radial_open_reference_v0_7"]["constructor_id"]
    bundle.constructors[constructor_id]["edge_families"]["blade_root_to_hub"]["default_treatment"] = "blend"

    with pytest.raises(
        ValueError,
        match=(
            f"constructor {constructor_id} edge family blade_root_to_hub "
            "has unsupported default_treatment blend"
        ),
    ):
        dsl_resources._validate_bundle(bundle)


def test_v07_validation_requires_preset_radius_parameters_for_edge_families():
    bundle = copy.deepcopy(load_impeller_dsl_bundle("v0_7"))
    del bundle.presets["radial_open_reference_v0_7"]["parameter_values"]["root_fillet_radius_mm"]

    with pytest.raises(
        ValueError,
        match=(
            "preset radial_open_reference_v0_7 missing edge-family radius parameter "
            "root_fillet_radius_mm for constructor "
            "axisymmetric_throughflow_radial_bladed.open.v0_7 edge family blade_root_to_hub"
        ),
    ):
        dsl_resources._validate_bundle(bundle)


def test_v07_bounded_export_uses_deferred_surface_graph_mesh_route(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    model_output_root = tmp_path / "Model Output"
    calls = []

    def fake_graph_exports(step_path, stl_path, solid_name, surface_graph, view_id="cad_review_360"):
        calls.append((Path(step_path), Path(stl_path), solid_name, surface_graph, view_id))
        Path(step_path).write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        Path(stl_path).write_text("solid impeller\nendsolid impeller\n", encoding="utf-8")
        return {
            "step": {"source": "surface_graph", "export_exactness": "surface_graph_mesh_step"},
            "stl": {"source": "surface_graph", "export_exactness": "surface_graph_sampled_mesh"},
        }

    def fail_support_face_export(*_args, **_kwargs):
        raise AssertionError("V0.7 Task 2 route must not use the V0.6 support-face BREP writer")

    monkeypatch.setattr(service_module, "write_surface_graph_exports", fake_graph_exports)
    monkeypatch.setattr(service_module, "write_trimmed_brep_step", fail_support_face_export)

    exports, export_manifests = service_module._write_exports(
        run_dir,
        "impeller",
        {},
        dsl_context={
            "preset_id": "radial_open_reference_v0_7",
            "export_contract": {"mode": "surface_graph_bounded_brep", "default_view": "cad_review_360"},
        },
        geometry_metadata={
            "surface_graph": {
                "surfaces": [
                    {
                        "id": "hub",
                        "feature_id": "hub_material_solid",
                        "role": "hub",
                        "uv_grid": [
                            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                            [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
                        ],
                    }
                ]
            }
        },
        model_output_root=model_output_root,
    )

    assert len(calls) == 1
    assert Path(exports["step"]).parent == model_output_root
    assert Path(exports["stl"]).parent == model_output_root
    assert Path(exports["manifest"]).parent == model_output_root
    assert export_manifests["step"]["export_exactness"] == "surface_graph_mesh_step"
    assert export_manifests["step"]["bounded_brep_status"] == "deferred_until_bounded_face_export"
    assert export_manifests["step"]["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert export_manifests["stl"]["export_exactness"] == "surface_graph_sampled_mesh"

    strategy = service_module._export_strategy(
        "impeller",
        dsl_context={"export_contract": {"mode": "surface_graph_bounded_brep", "default_view": "cad_review_360"}},
    )
    assert strategy["mode"] == "surface_graph_bounded_brep"
    assert strategy["cad_exports"] == "deferred"
    assert strategy["step_exactness"] == "surface_graph_mesh_step"
    assert strategy["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert strategy["step_exactness"] != strategy["target_step_exactness"]


def test_v07_service_instantiates_bounded_brep_as_deferred_mesh_bridge(tmp_path):
    model_output_root = tmp_path / "model-output"
    service = service_module.RuleSynthesisService(tmp_path / "workspace", model_output_root=model_output_root)

    engine = service.synthesize("impeller", "radial_open_reference_v0_7")
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest

    assert manifest["preset_id"] == "radial_open_reference_v0_7"
    assert manifest["export_strategy"]["mode"] == "surface_graph_bounded_brep"
    assert manifest["export_strategy"]["cad_exports"] == "deferred"
    assert manifest["export_strategy"]["step_exactness"] == "surface_graph_mesh_step"
    assert manifest["export_strategy"]["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert manifest["export_strategy"]["step_exactness"] != manifest["export_strategy"]["target_step_exactness"]
    assert manifest["export_strategy"]["bounded_brep_status"] == "deferred_until_bounded_face_export"

    export_contract = manifest["export_strategy"]["export_contract"]
    assert export_contract["step_exactness"] == "surface_graph_mesh_step"
    assert export_contract["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert export_contract["bounded_brep_status"] == "deferred_until_bounded_face_export"

    step_manifest = manifest["export_manifests"]["step"]
    assert step_manifest["export_exactness"] == "surface_graph_mesh_step"
    assert step_manifest["bounded_brep_status"] == "deferred_until_bounded_face_export"
    assert step_manifest["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert "step_is_surface_graph_mesh_not_trimmed_brep" in step_manifest["limitations"]

    step_path = Path(manifest["exports"]["step"])
    stl_path = Path(manifest["exports"]["stl"])
    manifest_path = Path(manifest["exports"]["manifest"])
    assert step_path.parent == model_output_root
    assert step_path.exists()
    assert stl_path.exists()
    assert manifest_path.exists()
