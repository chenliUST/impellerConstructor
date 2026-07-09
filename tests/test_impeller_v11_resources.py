from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_runtime_compiler import (
    compile_impeller_runtime_preset,
    impeller_json_preset_ids,
)
from part_rule_synthesis.impeller_v11_constants import SOURCE_KERNEL


def test_v111_active_backend_preset_catalog():
    ids = {preset_id for preset_id in impeller_json_preset_ids() if preset_id.endswith("_v1_1")}

    assert ids == {
        "radial_open_reference_v1_1",
        "radial_closed_reference_v1_1",
        "nasa_stage37_stator_ring_v1_1",
        "rr_ultrafan_cti_fan_v1_1",
        "public_rocket_turbopump_inducer_v1_1",
    }


def test_v111_open_reference_uses_eight_main_and_eight_splitters():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]

    assert runtime["geometry_version"] == "1.1"
    assert runtime["geometry_patch_version"] == "1.1.2"
    assert runtime["math_parameterization"] == "v1_1_2_canonical_nurbs_parameterization"
    assert runtime["source_kernel"] == SOURCE_KERNEL
    assert "canonical_nurbs_parameterization" in runtime
    assert runtime["mesh_strategy"] == "v1_1_1_all_surface_uv_grid_mesh"
    assert runtime["parameters"]["blade_count"]["default"] == 16
    assert defaults["main_blade_count"] == 8
    assert defaults["splitter_blade_count"] == 8
    assert defaults["splitter_positioning_mode"] == "main_passage_bisector"
    assert defaults["splitter_passage_fraction"] == 0.5


def test_v111_export_contract_advertises_all_surface_mesh_strategy():
    runtime = compile_impeller_runtime_preset("radial_open_reference_v1_1")
    contract = runtime["export_contract"]

    assert contract["mesh_strategy"] == "v1_1_1_all_surface_uv_grid_mesh"
    assert contract["supported_mesh_strategies"] == ["v1_1_1_all_surface_uv_grid_mesh"]


def test_v111_closed_reference_uses_twelve_full_blades_no_splitters():
    runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]

    assert runtime["geometry_patch_version"] == "1.1.2"
    assert runtime["math_parameterization"] == "v1_1_2_canonical_nurbs_parameterization"
    assert "canonical_nurbs_parameterization" in runtime
    assert runtime["facets"]["shroud_topology"] == "closed"
    assert runtime["parameters"]["blade_count"]["default"] == 12
    assert defaults["main_blade_count"] == 12
    assert defaults["splitter_blade_count"] == 0
    assert defaults["tip_attachment_mode"] == "closed_shroud_attachment"
    assert runtime["parameters"]["hood_wall_thickness_mm"]["default"] > 0.0


def test_v111_public_presets_use_v11_surface_family_language():
    for preset_id in [
        "nasa_stage37_stator_ring_v1_1",
        "rr_ultrafan_cti_fan_v1_1",
        "public_rocket_turbopump_inducer_v1_1",
    ]:
        runtime = compile_impeller_runtime_preset(preset_id)
        defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]

        assert runtime["geometry_version"] == "1.1"
        assert runtime["geometry_patch_version"] == "1.1.2"
        assert runtime["math_parameterization"] == "v1_1_2_canonical_nurbs_parameterization"
        assert "canonical_nurbs_parameterization" in runtime
        assert (
            runtime["transition_geometry_status"]
            == "topology_first_blade_to_blade_5_loop_surface_family_graph"
        )
        assert runtime["constructor_id"].endswith("_v1_1")
        assert defaults["coordinate_system"] == "blade_to_blade_s_q_mm"
        assert defaults["main_blade_count"] == runtime["parameters"]["blade_count"]["default"]
        assert defaults["splitter_blade_count"] == 0
        assert defaults["side_sample_count"] >= 49
        assert defaults["edge_cap_sample_count"] >= 33


def test_v111_rr_ultrafan_preset_uses_export_stable_dense_sampling():
    runtime = compile_impeller_runtime_preset("rr_ultrafan_cti_fan_v1_1")
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]

    assert runtime["geometry_patch_version"] == "1.1.2"
    assert runtime["math_parameterization"] == "v1_1_2_canonical_nurbs_parameterization"
    assert "canonical_nurbs_parameterization" in runtime
    assert defaults["side_sample_count"] >= 81
    assert defaults["surface_span_sample_count"] >= 13
    assert defaults["edge_cap_sample_count"] >= 33
