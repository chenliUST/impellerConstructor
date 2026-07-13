from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_dsl_resources import load_impeller_dsl_bundle
from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
from part_rule_synthesis.impeller_v11_5_engineering_drawing import build_engineering_drawing_contract
from part_rule_synthesis.service import RuleSynthesisService


PRESET_ID = "ks007g23b_turbine_impeller_v1_1"
STEP_PRESET_ID = "ks007g23b_step_reconstructed_v1_1"


def test_ks007g23b_resource_preserves_drawing_provenance_and_confidence():
    bundle = load_impeller_dsl_bundle("v1_1")
    preset = bundle.presets[PRESET_ID]

    assert bundle.aliases["KS007G23B"] == PRESET_ID
    assert preset["source_metadata"]["drawing_no"] == "KS007G23B"
    assert preset["source_metadata"]["source_kind"] == "customer_supplied_2d_part_drawing"
    assert preset["source_metadata"]["missing_authority"] == "referenced_3d_model_not_supplied"
    assert preset["parameter_values"]["blade_count"] == 13
    assert preset["blade_to_blade_loop_family_defaults"]["main_blade_count"] == 13
    assert preset["blade_to_blade_loop_family_defaults"]["splitter_blade_count"] == 0

    confidence = preset["parameter_confidence"]
    assert {f"parameter_values.{name}" for name in preset["parameter_values"]} <= set(confidence)
    assert confidence["parameter_values.blade_count"]["confidence"] >= 0.99
    assert confidence["parameter_values.exit_radius_mm"]["confidence"] >= 0.99
    assert confidence["parameter_values.mounting_bore_radius_mm"]["confidence"] >= 0.85
    assert confidence["parameter_values.blade_wrap_deg"]["confidence"] <= 0.50
    assert confidence["blade_to_blade_loop_family_defaults.hub_profile_rz_mm"]["confidence"] <= 0.65
    assert confidence["blade_to_blade_loop_family_defaults.tip_or_shroud_profile_rz_mm"]["confidence"] <= 0.65


def test_ks007g23b_compiles_and_instantiates_as_review_grade(tmp_path):
    runtime = compile_impeller_runtime_preset(PRESET_ID)
    assert runtime["preset_id"] == PRESET_ID
    assert runtime["parameters"]["blade_count"]["default"] == 13
    assert runtime["resolved_blade_to_blade_loop_family_defaults"]["splitter_blade_count"] == 0
    assert runtime["source_metadata"]["drawing_no"] == "KS007G23B"
    assert runtime["parameter_confidence"]["parameter_values.blade_count"]["confidence"] == 1.0

    service = RuleSynthesisService(tmp_path / "runs")
    engine = service.synthesize("impeller", preset_id=PRESET_ID)
    run = service.instantiate(engine.engine_id, {}, geometry_stage="edge_closures")
    assert run.manifest["preset_id"] == PRESET_ID
    assert run.manifest["geometry_validation_status"] == "PASS"
    assert run.manifest["source_metadata"]["drawing_no"] == "KS007G23B"
    contract = build_engineering_drawing_contract(
        run.manifest["geometry"]["surface_graph"],
        preset_id=PRESET_ID,
        source_metadata=run.manifest["source_metadata"],
        parameter_confidence=run.manifest["parameter_confidence"],
    )
    quality_rows = contract["construction_tables"]["quality_constraints"]["rows"]
    blade_count_row = next(row for row in quality_rows if row.get("parameter") == "parameter_values.blade_count")
    assert blade_count_row["confidence"] == 1.0
    assert blade_count_row["basis"] == "direct"


def test_ks007g23b_step_resource_preserves_brep_measurements_and_mapping_loss():
    bundle = load_impeller_dsl_bundle("v1_1")
    preset = bundle.presets[STEP_PRESET_ID]

    assert bundle.aliases["KS007G23B_STEP"] == STEP_PRESET_ID
    assert preset["source_metadata"]["source_kind"] == "customer_supplied_step_brep"
    assert preset["source_metadata"]["source_sha256"] == (
        "1010f341320ce9d98f5ab6456611f73d47dfcc270969a042e8ed10647f1a59f5"
    )
    analysis = preset["source_metadata"]["step_brep_analysis"]
    assert analysis["solid_count"] == 1
    assert analysis["face_count"] == 240
    assert analysis["periodic_blade_count"] == 13
    assert analysis["outer_radius_mm"] == 51.6
    assert analysis["overall_axial_extent_mm"] == 36.5
    assert analysis["main_cylindrical_bore_radius_mm"] == 7.9
    assert "not STEP-equivalent CAD" in preset["source_metadata"]["mapping_loss"]

    assert preset["parameter_values"]["blade_thickness_mm"] == 5.2
    assert preset["parameter_values"]["blade_wrap_deg"] == 32.0
    assert preset["blade_to_blade_loop_family_defaults"]["maximum_blade_thickness_mm"] == 6.6
    assert preset["blade_to_blade_loop_family_defaults"]["hub_profile_rz_mm"][0] == [12.5, 25.0]
    assert preset["blade_to_blade_loop_family_defaults"]["tip_or_shroud_profile_rz_mm"][-1] == [51.5001, 5.3997]

    confidence = preset["parameter_confidence"]
    assert confidence["parameter_values.blade_thickness_mm"]["confidence"] >= 0.9
    assert confidence["parameter_values.blade_wrap_deg"]["confidence"] >= 0.9
    assert confidence["blade_to_blade_loop_family_defaults.hub_profile_rz_mm"]["confidence"] >= 0.9
    assert confidence["parameter_values.root_fillet_radius_mm"]["confidence"] < 0.6


def test_ks007g23b_step_preset_compiles_with_exact_population_contract():
    runtime = compile_impeller_runtime_preset(STEP_PRESET_ID)
    defaults = runtime["resolved_blade_to_blade_loop_family_defaults"]

    assert runtime["preset_id"] == STEP_PRESET_ID
    assert runtime["parameters"]["blade_count"]["default"] == 13
    assert defaults["main_blade_count"] == 13
    assert defaults["splitter_blade_count"] == 0
    assert runtime["source_metadata"]["step_brep_analysis"]["volume_mm3"] == 61526.200588
