from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

RUNTIME_RELEASE_VERSION = "1.1.3"
INSPECTION_CONTRACT_VERSION = "1.1.3"


def validate_parameter_inspection_contract(
    surface_graph: Mapping[str, Any],
    contract: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(contract, Mapping):
        return [{"reason": "parameter_inspection_contract_unsupported"}]
    failures: list[dict[str, Any]] = []
    if contract.get("contract_version") != INSPECTION_CONTRACT_VERSION:
        failures.append({"reason": "parameter_inspection_contract_unsupported"})
    expected_generation_id = parameter_inspection_generation_id(surface_graph)
    if (
        surface_graph.get("generation_id") != expected_generation_id
        or contract.get("generation_id") != expected_generation_id
    ):
        failures.append({"reason": "parameter_inspection_generation_id_mismatch"})

    blade_instances = contract.get("blade_instances")
    surface_references = contract.get("surface_references")
    span_stations = contract.get("span_stations")
    section_loops = contract.get("section_loops")
    support_profiles = contract.get("support_profiles")
    resolved_dimensions = contract.get("resolved_dimensions")
    continuity_measurements = contract.get("continuity_measurements")
    collections = (
        blade_instances,
        surface_references,
        span_stations,
        section_loops,
        support_profiles,
        resolved_dimensions,
        continuity_measurements,
    )
    graph_surfaces = surface_graph.get("surfaces")
    if not all(isinstance(collection, Mapping) for collection in collections) or not isinstance(graph_surfaces, list):
        return [{"reason": "parameter_inspection_contract_unsupported"}]
    if not _mapping_records_are_well_formed(blade_instances, "blade_instance_id"):
        return [{"reason": "parameter_inspection_contract_unsupported"}]
    if not _mapping_records_are_well_formed(surface_references, "surface_id"):
        return [{"reason": "parameter_inspection_contract_unsupported"}]
    if not _mapping_records_are_well_formed(span_stations, "span_station_id"):
        return [{"reason": "parameter_inspection_contract_unsupported"}]
    if not _mapping_records_are_well_formed(section_loops, "section_loop_id"):
        return [{"reason": "parameter_inspection_contract_unsupported"}]
    if not _support_profiles_are_well_formed(support_profiles) or not _dimensions_are_well_formed(resolved_dimensions):
        return [{"reason": "parameter_inspection_contract_unsupported"}]

    graph_surface_ids = {
        surface.get("id")
        for surface in graph_surfaces
        if isinstance(surface, Mapping) and _nonempty_string(surface.get("id"))
    }
    if len(graph_surface_ids) != len(graph_surfaces):
        return [{"reason": "parameter_inspection_contract_unsupported"}]
    referenced_surface_ids = set(surface_references)
    if graph_surface_ids != referenced_surface_ids:
        failures.append({"reason": "parameter_inspection_surface_reference_missing"})

    if not _surface_relationships_are_valid(blade_instances, surface_references):
        failures.append({"reason": "parameter_inspection_surface_reference_missing"})
    if not _station_relationships_are_valid(blade_instances, span_stations, section_loops):
        failures.append({"reason": "parameter_inspection_station_reference_missing"})
    if set(continuity_measurements) != set(section_loops) or any(
        not isinstance(measurement, Mapping) for measurement in continuity_measurements.values()
    ):
        return [{"reason": "parameter_inspection_contract_unsupported"}]

    control_point_ids: set[str] = set()
    segment_ids: set[str] = set()
    for loop in section_loops.values():
        if not _loop_record_is_well_formed(loop, control_point_ids, segment_ids):
            return [{"reason": "parameter_inspection_contract_unsupported"}]
        if not _loop_is_closed(loop):
            failures.append(
                {
                    "reason": "parameter_inspection_loop_not_closed",
                    "section_loop_id": loop.get("section_loop_id"),
                }
            )
    return failures


def parameter_inspection_generation_id(surface_graph: Mapping[str, Any]) -> str:
    basis = copy.deepcopy(dict(surface_graph))
    basis.pop("generation_id", None)
    basis.pop("parameter_inspection", None)
    surfaces = basis.get("surfaces")
    if isinstance(surfaces, list):
        for surface in surfaces:
            if isinstance(surface, dict) and _is_explicit_hidden_reference_surface(surface):
                surface["uv_grid"] = []
    encoded = json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _is_explicit_hidden_reference_surface(surface: Mapping[str, Any]) -> bool:
    surface_flags = surface.get("surface_flags")
    display = surface.get("display")
    reference_only = (
        isinstance(surface_flags, Mapping) and surface_flags.get("reference_only") is True
    ) or (
        isinstance(display, Mapping) and display.get("reference_only") is True
    )
    explicitly_hidden = isinstance(display, Mapping) and display.get("visible_by_default") is False
    return reference_only and explicitly_hidden


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
            metric_scale = float(loop.get("streamwise_metric_scale_mm"))
            segment_references = {}
            for name, segment in loop.get("segments", {}).items():
                segment_id = f"{loop_id}:{name}"
                source_points = copy.deepcopy(segment.get("points_s_q", []))
                source_controls = copy.deepcopy(segment.get("control_points_s_q", []))
                segment_references[name] = {
                    "section_segment_id": segment_id,
                    "source_segment_name": name,
                    "points_s_q": source_points,
                    "control_points_s_q": source_controls,
                    "display_points_s_q_mm": _metric_s_q_points(source_points, metric_scale),
                    "display_control_points_s_q_mm": _metric_s_q_points(source_controls, metric_scale),
                    "control_points": _control_point_records(segment_id, source_controls, metric_scale),
                }
            section_loops[loop_id] = {
                "section_loop_id": loop_id,
                "span_station_id": station_id,
                "source_blade_index": blade_index,
                "source_loop_index": loop_index,
                "source_coordinate_units": {"s": "normalized", "q": "mm"},
                "display_coordinate_units": {"s": "mm", "q": "mm"},
                "streamwise_metric_scale_mm": metric_scale,
                "segment_references": segment_references,
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


def _metric_s_q_points(points: Any, metric_scale: float) -> list[list[float]]:
    return [
        [float(point[0]) * metric_scale, float(point[1])]
        for point in points
    ]


def _control_point_records(
    section_segment_id: str,
    control_points: list[list[float]],
    metric_scale: float,
) -> list[dict[str, Any]]:
    digest_counts: dict[str, int] = {}
    records = []
    for point in control_points:
        encoded = json.dumps(point, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()[:12]
        occurrence = digest_counts.get(digest, 0)
        digest_counts[digest] = occurrence + 1
        suffix = f"_{occurrence}" if occurrence else ""
        records.append(
            {
                "control_point_id": f"{section_segment_id}:control_{digest}{suffix}",
                "section_segment_id": section_segment_id,
                "coordinates_s_q": copy.deepcopy(point),
                "display_coordinates_s_q_mm": [float(point[0]) * metric_scale, float(point[1])],
            }
        )
    return records


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _mapping_records_are_well_formed(records: Mapping[str, Any], id_field: str) -> bool:
    return all(
        _nonempty_string(record_id)
        and isinstance(record, Mapping)
        and record.get(id_field) == record_id
        for record_id, record in records.items()
    )


def _string_id_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(_nonempty_string(item) for item in value)
        and len(value) == len(set(value))
    )


def _surface_relationships_are_valid(
    blade_instances: Mapping[str, Any],
    surface_references: Mapping[str, Any],
) -> bool:
    for blade_id, blade in blade_instances.items():
        surface_ids = blade.get("surface_ids")
        if not _string_id_list(surface_ids):
            return False
        if any(
            surface_id not in surface_references
            or surface_references[surface_id].get("blade_instance_id") != blade_id
            for surface_id in surface_ids
        ):
            return False
    for surface_id, reference in surface_references.items():
        if not isinstance(reference.get("quality"), Mapping):
            return False
        blade_id = reference.get("blade_instance_id")
        if blade_id is None:
            continue
        if not _nonempty_string(blade_id) or blade_id not in blade_instances:
            return False
        if surface_id not in blade_instances[blade_id].get("surface_ids", []):
            return False
    return True


def _station_relationships_are_valid(
    blade_instances: Mapping[str, Any],
    span_stations: Mapping[str, Any],
    section_loops: Mapping[str, Any],
) -> bool:
    for blade_id, blade in blade_instances.items():
        station_ids = blade.get("span_station_ids")
        if not _string_id_list(station_ids):
            return False
        if any(
            station_id not in span_stations
            or span_stations[station_id].get("blade_instance_id") != blade_id
            for station_id in station_ids
        ):
            return False
    for station_id, station in span_stations.items():
        blade_id = station.get("blade_instance_id")
        loop_id = station.get("section_loop_id")
        if (
            not _nonempty_string(blade_id)
            or blade_id not in blade_instances
            or station_id not in blade_instances[blade_id].get("span_station_ids", [])
            or not _nonempty_string(loop_id)
            or loop_id not in section_loops
            or section_loops[loop_id].get("span_station_id") != station_id
        ):
            return False
    return all(
        _nonempty_string(loop.get("span_station_id"))
        and loop["span_station_id"] in span_stations
        and span_stations[loop["span_station_id"]].get("section_loop_id") == loop_id
        for loop_id, loop in section_loops.items()
    )


def _support_profiles_are_well_formed(profiles: Mapping[str, Any]) -> bool:
    return all(
        _nonempty_string(profile_id)
        and isinstance(profile, Mapping)
        and profile.get("id") == profile_id
        and _point_array(profile.get("control_points"))
        and profile.get("coordinate_system") == "rz_meridional_mm"
        for profile_id, profile in profiles.items()
    )


def _dimensions_are_well_formed(dimensions: Mapping[str, Any]) -> bool:
    return all(
        _nonempty_string(dimension_id)
        and isinstance(dimension, Mapping)
        and _nonempty_string(dimension.get("unit"))
        and _nonempty_string(dimension.get("requested_unit"))
        for dimension_id, dimension in dimensions.items()
    )


def _loop_record_is_well_formed(
    loop: Mapping[str, Any],
    control_point_ids: set[str],
    segment_ids: set[str],
) -> bool:
    metric_scale = loop.get("streamwise_metric_scale_mm")
    if (
        loop.get("source_coordinate_units") != {"s": "normalized", "q": "mm"}
        or loop.get("display_coordinate_units") != {"s": "mm", "q": "mm"}
        or not _finite_number(metric_scale)
        or float(metric_scale) <= 0
        or not isinstance(loop.get("metrics"), Mapping)
        or not isinstance(loop.get("join_metrics"), Mapping)
        or not isinstance(loop.get("segment_references"), Mapping)
        or not loop["segment_references"]
    ):
        return False
    for segment_name, segment in loop["segment_references"].items():
        if not _segment_record_is_well_formed(
            segment_name,
            segment,
            float(metric_scale),
            control_point_ids,
            segment_ids,
        ):
            return False
    return True


def _segment_record_is_well_formed(
    segment_name: str,
    segment: Any,
    metric_scale: float,
    control_point_ids: set[str],
    segment_ids: set[str],
) -> bool:
    if not isinstance(segment, Mapping) or segment.get("source_segment_name") != segment_name:
        return False
    segment_id = segment.get("section_segment_id")
    points = segment.get("points_s_q")
    controls = segment.get("control_points_s_q")
    display_points = segment.get("display_points_s_q_mm")
    display_controls = segment.get("display_control_points_s_q_mm")
    control_records = segment.get("control_points")
    if (
        not _nonempty_string(segment_id)
        or segment_id in segment_ids
        or not _point_array(points)
        or not _point_array(controls)
        or not _point_array(display_points)
        or not _point_array(display_controls)
        or not isinstance(control_records, list)
        or len(control_records) != len(controls)
        or not _metric_points_match(points, display_points, metric_scale)
        or not _metric_points_match(controls, display_controls, metric_scale)
    ):
        return False
    segment_ids.add(segment_id)
    for source_point, record in zip(controls, control_records):
        if not isinstance(record, Mapping):
            return False
        control_id = record.get("control_point_id")
        if (
            not _nonempty_string(control_id)
            or control_id in control_point_ids
            or record.get("section_segment_id") != segment_id
            or not _point(record.get("coordinates_s_q"))
            or list(record["coordinates_s_q"]) != list(source_point)
            or not _point(record.get("display_coordinates_s_q_mm"))
            or not _metric_points_match(
                [record["coordinates_s_q"]],
                [record["display_coordinates_s_q_mm"]],
                metric_scale,
            )
        ):
            return False
        control_point_ids.add(control_id)
    return True


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _point(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(_finite_number(coordinate) for coordinate in value)


def _point_array(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_point(point) for point in value)


def _metric_points_match(source: list[Any], display: list[Any], metric_scale: float) -> bool:
    return len(source) == len(display) and all(
        math.isclose(float(metric[0]), float(point[0]) * metric_scale, rel_tol=0.0, abs_tol=1.0e-9)
        and math.isclose(float(metric[1]), float(point[1]), rel_tol=0.0, abs_tol=1.0e-9)
        for point, metric in zip(source, display)
    )


def _loop_is_closed(loop: Mapping[str, Any]) -> bool:
    if loop.get("metrics", {}).get("join_status") != "PASS":
        return False
    segments = loop.get("segment_references", {})
    try:
        pressure = segments["pressure_side"]["points_s_q"]
        leading = segments["leading_edge"]["points_s_q"]
        suction = segments["suction_side"]["points_s_q"]
        trailing = segments["trailing_edge"]["points_s_q"]
    except (KeyError, TypeError):
        return False
    joins = (
        (pressure[0], leading[0]),
        (leading[-1], suction[0]),
        (suction[-1], trailing[-1]),
        (trailing[0], pressure[-1]),
    )
    return all(
        math.isclose(float(left[0]), float(right[0]), rel_tol=0.0, abs_tol=1.0e-7)
        and math.isclose(float(left[1]), float(right[1]), rel_tol=0.0, abs_tol=1.0e-7)
        for left, right in joins
    )


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
