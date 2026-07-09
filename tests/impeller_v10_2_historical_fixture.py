from __future__ import annotations

import copy
from typing import Any

from part_rule_synthesis.impeller_runtime_compiler import (
    _v10_2_attachment_defaults,
    _v10_2_feasibility_constraints,
    compile_impeller_runtime_preset,
)
from part_rule_synthesis.service import _bind_parameters, _geometry_metadata


def historical_v10_2_runtime(preset_id: str = "radial_open_reference_v1_0") -> dict[str, Any]:
    runtime = dict(compile_impeller_runtime_preset(preset_id))
    if (
        preset_id == "radial_open_reference_v1_0"
        and runtime.get("geometry_patch_version") != "1.0.2"
    ):
        historical_contract_runtime = compile_impeller_runtime_preset("radial_closed_reference_v1_0")
        attachment_defaults = _v10_2_attachment_defaults(
            runtime["parameters"],
            runtime["dsl_sections"],
        )
        runtime["geometry_patch_version"] = "1.0.2"
        runtime["transition_geometry_status"] = "topology_first_closed_nurbs_impeller_surface_graph"
        runtime["selected_rules"] = copy.deepcopy(historical_contract_runtime["selected_rules"])
        runtime["export_contract"] = copy.deepcopy(historical_contract_runtime["export_contract"])
        runtime["mesh_strategy"] = historical_contract_runtime["mesh_strategy"]
        runtime["kernel_capability_matrix_id"] = "impeller_v1_0_kernel_capabilities"
        runtime["golden_case_registry_id"] = "impeller_v1_0_golden_cases"
        runtime["resolved_attachment_defaults"] = attachment_defaults
        runtime["continuous_blade_attachment_status"] = "configured"
        runtime["preset_feasibility_status"] = attachment_defaults["preset_feasibility_status"]
        runtime["preset_default_violation_count"] = attachment_defaults["preset_default_violation_count"]
        runtime["preset_feasibility_constraints"] = _v10_2_feasibility_constraints(runtime["dsl_sections"])
        runtime["preset_adjusted_defaults"] = {}
        runtime.pop("resolved_section_loop_defaults", None)
        runtime.pop("v1_0_3_preset_feasibility", None)
    return runtime


def historical_v10_2_metadata(preset_id: str = "radial_open_reference_v1_0") -> dict[str, Any]:
    runtime = historical_v10_2_runtime(preset_id)
    parameters = _bind_parameters(runtime, {})
    return _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )


def historical_v10_2_graph(preset_id: str = "radial_open_reference_v1_0") -> dict[str, Any]:
    return historical_v10_2_metadata(preset_id)["surface_graph"]


def historical_v10_2_graph_tuple(
    preset_id: str = "radial_open_reference_v1_0",
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    runtime = historical_v10_2_runtime(preset_id)
    parameters = _bind_parameters(runtime, {})
    metadata = _geometry_metadata(
        "impeller",
        parameters,
        runtime["facets"],
        dsl_context=runtime,
    )
    graph = metadata["surface_graph"]
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}
    return graph, surfaces, runtime
