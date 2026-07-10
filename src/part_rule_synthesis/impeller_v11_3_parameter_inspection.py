from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

RUNTIME_RELEASE_VERSION = "1.1.3"
INSPECTION_CONTRACT_VERSION = "1.1.3"


def parameter_inspection_generation_id(surface_graph: Mapping[str, Any]) -> str:
    basis = {
        "geometry_patch_version": surface_graph.get("geometry_patch_version"),
        "canonical": surface_graph.get("canonical_nurbs_parameterization", {}),
        "surfaces": [
            {
                "id": surface.get("id"),
                "role": surface.get("role"),
                "uv_grid": surface.get("uv_grid", []),
            }
            for surface in surface_graph.get("surfaces", [])
        ],
    }
    encoded = json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def build_parameter_inspection_contract(surface_graph: Mapping[str, Any]) -> dict[str, Any]:
    generation_id = parameter_inspection_generation_id(surface_graph)
    canonical = surface_graph.get("canonical_nurbs_parameterization", {})
    loop_family = surface_graph.get("blade_to_blade_loop_family", {})
    surfaces = surface_graph.get("surfaces", [])
    surface_references = {
        str(surface["id"]): {
            "surface_id": str(surface["id"]),
            "blade_instance_id": _blade_instance_id(surface.get("blade_index")),
            "blade_index": surface.get("blade_index"),
            "face_family": surface.get("face_family"),
            "role": surface.get("role"),
            "quality": copy.deepcopy(
                surface.get("v1_1_root_quality")
                or surface.get("v1_1_tip_quality")
                or surface.get("v1_1_span_domain_quality")
                or {}
            ),
        }
        for surface in surfaces
        if surface.get("id")
    }
    blade_instances: dict[str, Any] = {}
    span_stations: dict[str, Any] = {}
    section_loops: dict[str, Any] = {}
    for blade_index, blade in enumerate(loop_family.get("blades", [])):
        blade_id = _blade_instance_id(blade_index)
        blade_surface_ids = [
            surface_id
            for surface_id, reference in surface_references.items()
            if reference.get("blade_index") == blade_index
        ]
        station_ids = []
        for loop_index, loop in enumerate(blade.get("loops", [])):
            station_id = f"{blade_id}:span_{loop_index}"
            loop_id = f"{station_id}:loop"
            station_ids.append(station_id)
            span_stations[station_id] = {
                "span_station_id": station_id,
                "blade_instance_id": blade_id,
                "source_blade_index": blade_index,
                "source_loop_index": loop_index,
                "h": loop.get("h"),
                "active_span_fraction": loop.get("active_span_fraction"),
                "section_loop_id": loop_id,
            }
            section_loops[loop_id] = {
                "section_loop_id": loop_id,
                "span_station_id": station_id,
                "source_blade_index": blade_index,
                "source_loop_index": loop_index,
                "segment_references": {
                    name: {
                        "section_segment_id": f"{loop_id}:{name}",
                        "source_segment_name": name,
                        "points_s_q": copy.deepcopy(segment.get("points_s_q", [])),
                        "control_points_s_q": copy.deepcopy(segment.get("control_points_s_q", [])),
                    }
                    for name, segment in loop.get("segments", {}).items()
                },
                "metrics": copy.deepcopy(loop.get("metrics", {})),
                "join_metrics": copy.deepcopy(loop.get("join_metrics", {})),
            }
        blade_instances[blade_id] = {
            "blade_instance_id": blade_id,
            "blade_index": blade_index,
            "blade_class": blade.get("blade_class"),
            "blade_pair_index": blade.get("blade_pair_index"),
            "phase_offset_pitch": blade.get("phase_offset_pitch"),
            "surface_ids": blade_surface_ids,
            "span_station_ids": station_ids,
        }
    return {
        "contract_version": INSPECTION_CONTRACT_VERSION,
        "generation_id": generation_id,
        "source_geometry_patch_version": surface_graph.get("geometry_patch_version"),
        "source_canonical_payload_version": canonical.get("canonical_payload_version"),
        "blade_instances": blade_instances,
        "surface_references": surface_references,
        "span_stations": span_stations,
        "section_loops": section_loops,
        "support_profiles": copy.deepcopy(canonical.get("support_profiles", {})),
        "resolved_dimensions": _resolved_dimensions(surface_graph, canonical),
        "continuity_measurements": {
            loop_id: copy.deepcopy(loop["join_metrics"])
            for loop_id, loop in section_loops.items()
        },
    }


def _blade_instance_id(blade_index: Any) -> str | None:
    return None if blade_index is None else f"blade_{int(blade_index)}"


def _resolved_dimensions(surface_graph: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    metrics = surface_graph.get("canonical_metrics", {})
    thickness_controls = [
        float(point[2])
        for row in canonical.get("thickness_field", {}).get("control_points", [])
        for point in row
    ]
    population = canonical.get("blade_population", {})
    active_span = canonical.get("active_span_policy", {})
    return {
        "thickness_min_mm": _dimension(
            min(thickness_controls) if thickness_controls else None,
            metrics.get("thickness_min_mm"),
            "mm",
        ),
        "thickness_max_mm": _dimension(
            max(thickness_controls) if thickness_controls else None,
            metrics.get("thickness_max_mm"),
            "mm",
        ),
        "root_offset_mm": _dimension(
            active_span.get("root_offset", {}).get("ratio_of_local_thickness"),
            active_span.get("root_offset", {}).get("resolved_constant_mm"),
            "mm",
            requested_unit="thickness ratio",
        ),
        "tip_offset_mm": _dimension(
            active_span.get("tip_offset", {}).get("ratio_of_local_thickness"),
            active_span.get("tip_offset", {}).get("resolved_constant_mm"),
            "mm",
            requested_unit="thickness ratio",
        ),
        "main_blade_count": _dimension(population.get("main_blade_count"), population.get("main_blade_count"), "count"),
        "splitter_blade_count": _dimension(population.get("splitter_blade_count"), population.get("splitter_blade_count"), "count"),
        "splitter_passage_fraction": _dimension(
            population.get("splitter_passage_fraction"),
            population.get("splitter_passage_fraction"),
            "pitch fraction",
        ),
    }


def _dimension(
    requested_value: Any,
    resolved_value: Any,
    unit: str,
    *,
    requested_unit: str | None = None,
) -> dict[str, Any]:
    return {
        "requested_value": requested_value,
        "resolved_value": resolved_value,
        "unit": unit,
        "requested_unit": requested_unit or unit,
    }
