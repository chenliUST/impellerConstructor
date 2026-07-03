import copy
from pathlib import Path

import pytest

from part_rule_synthesis import impeller_dsl_resources as dsl_resources
from part_rule_synthesis import service as service_module
from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v07_bundle_loads_schema_and_transition_resources():
    bundle = load_impeller_dsl_bundle("v0_7")
    export_contract = bundle.export_contracts["surface_graph_bounded_brep"]

    assert bundle.schema["dsl_version"] == "0.7"
    assert bundle.shape_controls["shape_control_version"] == "0.7"
    assert set(bundle.presets) == {
        "radial_open_reference_v0_7",
        "radial_closed_reference_v0_7",
    }
    assert export_contract["mode"] == "surface_graph_bounded_brep"
    assert export_contract["step_exactness"] == "surface_graph_bounded_unsewn_brep_step"
    assert export_contract["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert export_contract["diagnostic_step_exactness"] == "surface_graph_bounded_unsewn_brep_step"
    assert export_contract["bounded_brep_status"] == "bounded_faces_unsewn"
    assert export_contract["coverage_status"] == "partial_supported_surfaces"
    assert export_contract["cad_export_scope"] == "supported_bounded_brep_surfaces"
    assert export_contract["unsupported_surface_policy"] == "excluded_with_manifest_accounting"
    assert export_contract["mesh_exports"] == ["stl", "obj"]
    assert export_contract["target_mesh_exports"] == ["mesh_manifest"]
    assert export_contract["experimental_exports"] == []


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
        expected_radius = (
            0.0
            if edge_family["default_treatment"] == "none"
            else float(preset["parameter_values"][radius_parameter])
        )
        assert policy["radius_mm"] == expected_radius


def test_v07_runtime_allows_axial_public_data_facet_studies():
    runtime = compile_impeller_runtime_preset(
        "radial_open_reference_v0_7",
        {
            "flow_topology": "axial",
            "shroud_topology": "open",
            "suction_topology": "single_suction",
            "blade_exit_geometry": "backward_curved",
            "working_domain": "fan_or_blower",
            "passage_topology": "throughflow_bladed_channel",
        },
    )

    assert runtime["facets"]["flow_topology"] == "axial"
    assert runtime["facets"]["working_domain"] == "fan_or_blower"
    assert runtime["dsl_sections"]["dsl_version"] == "0.7"
    assert "edge_families" in runtime


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


def test_v07_validation_requires_default_radius_parameter_to_be_string():
    bundle = copy.deepcopy(load_impeller_dsl_bundle("v0_7"))
    constructor_id = bundle.presets["radial_open_reference_v0_7"]["constructor_id"]
    bundle.constructors[constructor_id]["edge_families"]["blade_root_to_hub"]["default_radius_parameter"] = [
        "root_fillet_radius_mm"
    ]

    with pytest.raises(
        ValueError,
        match=(
            f"constructor {constructor_id} edge family blade_root_to_hub "
            "default_radius_parameter must be a string"
        ),
    ):
        dsl_resources._validate_bundle(bundle)


def test_v07_validation_rejects_nonnumeric_preset_radius_parameter_value():
    bundle = copy.deepcopy(load_impeller_dsl_bundle("v0_7"))
    bundle.presets["radial_open_reference_v0_7"]["parameter_values"]["root_fillet_radius_mm"] = "large"

    with pytest.raises(
        ValueError,
        match=(
            "preset radial_open_reference_v0_7 edge-family radius parameter "
            "root_fillet_radius_mm for constructor "
            "axisymmetric_throughflow_radial_bladed.open.v0_7 edge family blade_root_to_hub "
            "must be numeric"
        ),
    ):
        dsl_resources._validate_bundle(bundle)


def test_v07_validation_rejects_non_radius_default_radius_parameter():
    bundle = copy.deepcopy(load_impeller_dsl_bundle("v0_7"))
    constructor_id = bundle.presets["radial_open_reference_v0_7"]["constructor_id"]
    bundle.constructors[constructor_id]["edge_families"]["blade_root_to_hub"][
        "default_radius_parameter"
    ] = "blade_count"

    with pytest.raises(
        ValueError,
        match=(
            f"constructor {constructor_id} edge family blade_root_to_hub "
            "default_radius_parameter blade_count is not an allowed V0.7 transition-radius parameter"
        ),
    ):
        dsl_resources._validate_bundle(bundle)


def test_v07_bounded_export_routes_step_to_bounded_brep_and_hides_mesh_step(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    model_output_root = tmp_path / "Model Output"
    brep_calls = []
    mesh_calls = []
    obj_calls = []

    def fake_graph_exports(step_path, stl_path, solid_name, surface_graph, view_id="cad_review_360"):
        mesh_calls.append((Path(step_path), Path(stl_path), solid_name, surface_graph, view_id))
        Path(step_path).write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        Path(stl_path).write_text("solid impeller\nendsolid impeller\n", encoding="utf-8")
        return {
            "step": {"source": "surface_graph", "export_exactness": "surface_graph_mesh_step"},
            "stl": {"source": "surface_graph", "export_exactness": "surface_graph_sampled_mesh"},
        }

    def fake_bounded_brep(step_path, solid_name, surface_graph, view_id="cad_review_360"):
        brep_calls.append((Path(step_path), solid_name, surface_graph, view_id))
        Path(step_path).write_text("ISO-10303-21;\nADVANCED_FACE();\nEND-ISO-10303-21;\n", encoding="utf-8")
        return {
            "source": "surface_graph",
            "view": view_id,
            "export_exactness": "surface_graph_bounded_unsewn_brep_step",
            "target_exactness": "surface_graph_trimmed_brep_step",
            "bounded_face_count": len(surface_graph["surfaces"]),
            "sewing_status": "not_attempted",
        }

    def fake_obj_export(obj_path, solid_name, surface_graph, view_id="cad_review_360"):
        obj_calls.append((Path(obj_path), solid_name, surface_graph, view_id))
        Path(obj_path).write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
        return {
            "source": "surface_graph",
            "view": view_id,
            "export_exactness": "surface_graph_obj_mesh",
            "triangle_count": 1,
            "triangle_regions": [],
        }

    def fail_support_face_export(*_args, **_kwargs):
        raise AssertionError("V0.7 must not use the V0.6 support-face BREP writer")

    monkeypatch.setattr(service_module, "write_surface_graph_exports", fake_graph_exports)
    monkeypatch.setattr(service_module, "write_bounded_brep_step", fake_bounded_brep)
    monkeypatch.setattr(service_module, "write_surface_graph_obj", fake_obj_export)
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
                        "id": "bottom_cap",
                        "feature_id": "hub_material_solid",
                        "role": "hub",
                        "kind": "annular_plane_surface",
                        "outer_radius_mm": 10.0,
                        "inner_radius_mm": 2.0,
                        "z_mm": 0.0,
                        "uv_grid": [
                            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                            [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
                        ],
                    },
                    {
                        "id": "blade_surface",
                        "feature_id": "blade_0",
                        "role": "blade_pressure",
                        "kind": "lofted_blade_surface",
                        "uv_grid": [
                            [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]],
                            [[0.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
                        ],
                    },
                ]
            }
        },
        model_output_root=model_output_root,
    )

    assert len(brep_calls) == 1
    assert len(mesh_calls) == 1
    assert len(obj_calls) == 1
    assert Path(exports["step"]).parent == model_output_root
    assert Path(exports["stl"]).parent == model_output_root
    assert Path(exports["obj"]).parent == model_output_root
    assert Path(exports["manifest"]).parent == model_output_root
    assert "mesh_step" not in exports
    assert mesh_calls[0][0].parent.name == ".intermediate"
    assert [surface["id"] for surface in brep_calls[0][2]["surfaces"]] == ["bottom_cap"]
    assert export_manifests["step"]["export_exactness"] == "surface_graph_bounded_unsewn_brep_step"
    assert export_manifests["step"]["target_exactness"] == "surface_graph_trimmed_brep_step"
    assert export_manifests["step"]["bounded_brep_status"] == "bounded_faces_unsewn"
    assert export_manifests["step"]["included_surface_ids"] == ["bottom_cap"]
    assert export_manifests["step"]["excluded_surface_ids"] == ["blade_surface"]
    assert export_manifests["step"]["coverage_status"] == "partial_supported_surfaces"
    assert export_manifests["step"]["unsupported_surface_policy"] == "excluded_with_manifest_accounting"
    assert export_manifests["step"]["total_surface_count"] == 2
    assert export_manifests["step"]["supported_surface_count"] == 1
    assert export_manifests["step"]["unsupported_surface_count"] == 1
    assert export_manifests["stl"]["export_exactness"] == "surface_graph_sampled_mesh"
    assert export_manifests["obj"]["export_exactness"] == "surface_graph_obj_mesh"

    strategy = service_module._export_strategy(
        "impeller",
        dsl_context={"export_contract": {"mode": "surface_graph_bounded_brep", "default_view": "cad_review_360"}},
    )
    assert strategy["mode"] == "surface_graph_bounded_brep"
    assert strategy["cad_exports"] == "completed"
    assert strategy["step_exactness"] == "surface_graph_bounded_unsewn_brep_step"
    assert strategy["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert strategy["bounded_brep_status"] == "bounded_faces_unsewn"
    assert strategy["sewing_status"] == "not_attempted"
    assert strategy["coverage_status"] == "partial_supported_surfaces"
    assert strategy["cad_export_scope"] == "supported_bounded_brep_surfaces"
    assert strategy["unsupported_surface_policy"] == "excluded_with_manifest_accounting"
    assert strategy["step_exactness"] != strategy["target_step_exactness"]
    actual_strategy = service_module._export_strategy(
        "impeller",
        dsl_context={"export_contract": {"mode": "surface_graph_bounded_brep", "default_view": "cad_review_360"}},
        export_manifests={"step": {"export_exactness": "surface_graph_trimmed_brep_step"}},
    )
    assert actual_strategy["step_exactness"] == "surface_graph_trimmed_brep_step"
    assert actual_strategy["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert actual_strategy["diagnostic_step_exactness"] == "surface_graph_bounded_unsewn_brep_step"
    assert actual_strategy["export_contract"]["step_exactness"] == "surface_graph_bounded_unsewn_brep_step"


def test_v07_service_instantiates_bounded_brep_step_and_mesh_review_outputs(tmp_path):
    model_output_root = tmp_path / "model-output"
    service = service_module.RuleSynthesisService(tmp_path / "workspace", model_output_root=model_output_root)

    engine = service.synthesize("impeller", "radial_open_reference_v0_7")
    run = service.instantiate(engine.engine_id, {})
    manifest = run.manifest

    assert manifest["preset_id"] == "radial_open_reference_v0_7"
    assert manifest["export_strategy"]["mode"] == "surface_graph_bounded_brep"
    assert manifest["export_strategy"]["cad_exports"] == "completed"
    assert manifest["export_strategy"]["step_exactness"] == "surface_graph_trimmed_brep_step"
    assert manifest["export_strategy"]["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert manifest["export_strategy"]["diagnostic_step_exactness"] == "surface_graph_bounded_unsewn_brep_step"
    assert manifest["export_strategy"]["bounded_brep_status"] == "bounded_faces_unsewn"
    assert manifest["export_strategy"]["sewing_status"] == "not_attempted"
    assert manifest["export_strategy"]["coverage_status"] == "partial_supported_surfaces"
    assert manifest["export_strategy"]["cad_export_scope"] == "supported_bounded_brep_surfaces"
    assert manifest["export_strategy"]["unsupported_surface_policy"] == "excluded_with_manifest_accounting"

    export_contract = manifest["export_strategy"]["export_contract"]
    assert export_contract["step_exactness"] == "surface_graph_bounded_unsewn_brep_step"
    assert export_contract["target_step_exactness"] == "surface_graph_trimmed_brep_step"
    assert export_contract["bounded_brep_status"] == "bounded_faces_unsewn"
    assert export_contract["sewing_status"] == "not_attempted"
    assert export_contract["coverage_status"] == "partial_supported_surfaces"
    assert export_contract["cad_export_scope"] == "supported_bounded_brep_surfaces"
    assert export_contract["unsupported_surface_policy"] == "excluded_with_manifest_accounting"

    step_manifest = manifest["export_manifests"]["step"]
    assert step_manifest["export_exactness"] == "surface_graph_trimmed_brep_step"
    assert step_manifest["bounded_brep_status"] == "bounded_faces_unsewn"
    assert step_manifest["target_exactness"] == "surface_graph_trimmed_brep_step"
    assert {"name": "finite_reimport_bbox", "status": "PASS"} in step_manifest["validation_checks"]
    assert step_manifest["reimport_bbox"]["x_span_mm"] < 5000.0
    assert step_manifest["bounded_face_count"] > 0
    assert step_manifest["sewing_status"] == "not_attempted"
    assert step_manifest["coverage_status"] == "partial_supported_surfaces"
    assert step_manifest["unsupported_surface_policy"] == "excluded_with_manifest_accounting"
    assert step_manifest["total_surface_count"] > step_manifest["supported_surface_count"]
    assert step_manifest["supported_surface_count"] == step_manifest["bounded_face_count"]
    assert step_manifest["unsupported_surface_count"] == (
        step_manifest["total_surface_count"] - step_manifest["supported_surface_count"]
    )

    step_path = Path(manifest["exports"]["step"])
    stl_path = Path(manifest["exports"]["stl"])
    obj_path = Path(manifest["exports"]["obj"])
    manifest_path = Path(manifest["exports"]["manifest"])
    assert set(manifest["exports"]) == {"step", "stl", "obj", "manifest"}
    assert step_path.parent == model_output_root
    assert step_path.exists()
    assert stl_path.exists()
    assert obj_path.exists()
    assert manifest_path.exists()
