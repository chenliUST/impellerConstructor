from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset


def test_v06_bundle_loads_brep_export_contract():
    bundle = load_impeller_dsl_bundle("v0_6")

    assert bundle.schema["dsl_version"] == "0.6"
    assert "surface_graph_trimmed_brep" in bundle.export_contracts
    contract = bundle.export_contracts["surface_graph_trimmed_brep"]
    assert contract["mode"] == "surface_graph_brep"
    assert contract["step_exactness"] == "surface_graph_trimmed_nurbs_step"
    assert contract["mesh_step_exactness"] == "surface_graph_mesh_step"


def test_v06_open_and_closed_runtime_presets_compile():
    open_runtime = compile_impeller_runtime_preset("radial_open_reference_v0_6")
    closed_runtime = compile_impeller_runtime_preset("radial_closed_reference_v0_6")

    assert open_runtime["version"] == "0.6.0"
    assert closed_runtime["version"] == "0.6.0"
    assert open_runtime["export_contract"]["mode"] == "surface_graph_brep"
    assert closed_runtime["export_contract"]["mode"] == "surface_graph_brep"
    assert open_runtime["parameters"]["blade_count"]["default"] == 12
    assert closed_runtime["parameters"]["blade_count"]["default"] == 12
    assert "root_fillet_radius_mm" in open_runtime["parameters"]
    assert "leading_edge_radius_mm" in open_runtime["parameters"]
    assert "trailing_edge_radius_mm" in open_runtime["parameters"]


def test_v06_edge_radius_parameters_are_shape_controls():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v0_6")

    editable_variable_ids = {
        variable["id"] for variable in runtime["shape_control"]["editable_variables"]
    }
    semantic_handle_maps = {
        handle["id"]: handle["maps_to"]
        for handle in runtime["shape_control"]["semantic_handles"]
    }

    assert {
        "leading_edge_radius_mm",
        "trailing_edge_radius_mm",
        "tip_edge_radius_mm",
    } <= editable_variable_ids
    assert semantic_handle_maps["leading_edge_radius"] == ["leading_edge_radius_mm"]
    assert semantic_handle_maps["trailing_edge_radius"] == ["trailing_edge_radius_mm"]
    assert semantic_handle_maps["tip_edge_radius"] == ["tip_edge_radius_mm"]
