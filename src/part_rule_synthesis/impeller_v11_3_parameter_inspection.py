from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

RUNTIME_RELEASE_VERSION = "1.1.3"
INSPECTION_CONTRACT_VERSION = "1.1.3"

ENGINEERING_FEATURE_KINDS = {
    "nurbs_curve",
    "polyline",
    "control_point",
    "point",
    "local_frame",
    "reference_axis",
}
ENGINEERING_DIMENSION_KINDS = {
    "linear",
    "radial",
    "diameter",
    "angular",
    "arc_height",
    "ordinate",
    "control_coordinate",
}


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
    has_parameter_groups = "parameter_groups" in contract
    has_parameters = "parameters" in contract
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
    if has_parameter_groups != has_parameters:
        return [{"reason": "parameter_inspection_contract_unsupported"}]
    if has_parameter_groups and not _engineering_records_are_well_formed(
        contract["parameter_groups"], contract["parameters"]
    ):
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

    graph_surfaces_by_id = {surface["id"]: surface for surface in graph_surfaces}
    if not _surface_relationships_are_valid(blade_instances, surface_references, graph_surfaces_by_id):
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
            if isinstance(surface, dict) and not _surface_is_inspectable(surface):
                surface["uv_grid"] = []
    encoded = json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _surface_is_inspectable(surface: Mapping[str, Any]) -> bool:
    surface_flags = surface.get("surface_flags")
    display = surface.get("display")
    reference_only = (
        isinstance(surface_flags, Mapping) and surface_flags.get("reference_only") is True
    ) or (
        isinstance(display, Mapping) and display.get("reference_only") is True
    )
    explicitly_hidden = isinstance(display, Mapping) and display.get("visible_by_default") is False
    return not (reference_only and explicitly_hidden)


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
            "inspectable": _surface_is_inspectable(surface),
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
    resolved_dimensions = _resolved_dimensions(surface_graph, canonical)
    parameter_groups, parameters = _engineering_parameter_records(
        canonical,
        blade_instances,
        span_stations,
        section_loops,
        resolved_dimensions,
    )
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
        "resolved_dimensions": resolved_dimensions,
        "continuity_measurements": {
            loop_id: copy.deepcopy(loop["join_metrics"])
            for loop_id, loop in section_loops.items()
        },
        "parameter_groups": parameter_groups,
        "parameters": parameters,
    }


def _parameter_group(group_id: str, label: str, order: int, *, collapsed: bool = True) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "label": label,
        "order": order,
        "collapsed": collapsed,
    }


def _inspection_parameter(
    *,
    parameter_id: str,
    group_id: str,
    label: str,
    requested_value: Any,
    resolved_value: Any,
    unit: str,
    applicable_views: Sequence[str],
    feature_geometry: Sequence[Mapping[str, Any]],
    dimension_definition: Mapping[str, Any] | None,
    selection_scope: Mapping[str, Any],
    order: int,
) -> dict[str, Any]:
    return {
        "parameter_id": parameter_id,
        "group_id": group_id,
        "label": label,
        "requested_value": copy.deepcopy(requested_value),
        "resolved_value": copy.deepcopy(resolved_value),
        "unit": unit,
        "applicable_views": list(applicable_views),
        "feature_geometry": copy.deepcopy(list(feature_geometry)),
        "dimension_definition": copy.deepcopy(dimension_definition),
        "selection_scope": copy.deepcopy(dict(selection_scope)),
        "order": order,
    }


def _engineering_records_are_well_formed(parameter_groups: Any, parameters: Any) -> bool:
    if not isinstance(parameter_groups, list) or not parameter_groups or not isinstance(parameters, list):
        return False
    group_ids: set[str] = set()
    for group in parameter_groups:
        if (
            not isinstance(group, Mapping)
            or not _nonempty_string(group.get("group_id"))
            or group["group_id"] in group_ids
            or not _nonempty_string(group.get("label"))
            or not isinstance(group.get("order"), int)
            or isinstance(group["order"], bool)
            or not isinstance(group.get("collapsed"), bool)
        ):
            return False
        group_ids.add(group["group_id"])

    parameter_ids: set[str] = set()
    primitive_ids: set[str] = set()
    required_fields = {
        "parameter_id",
        "group_id",
        "label",
        "requested_value",
        "resolved_value",
        "unit",
        "applicable_views",
        "feature_geometry",
        "dimension_definition",
        "selection_scope",
        "order",
    }
    for parameter in parameters:
        if not isinstance(parameter, Mapping) or not required_fields <= set(parameter):
            return False
        parameter_id = parameter["parameter_id"]
        if (
            not _nonempty_string(parameter_id)
            or parameter_id in parameter_ids
            or parameter.get("group_id") not in group_ids
            or not _nonempty_string(parameter.get("label"))
            or not _nonempty_string(parameter.get("unit"))
            or not isinstance(parameter.get("order"), int)
            or isinstance(parameter["order"], bool)
            or not _engineering_value_is_finite(parameter["requested_value"])
            or not _engineering_value_is_finite(parameter["resolved_value"])
            or not _applicable_views_are_well_formed(parameter["applicable_views"])
            or not isinstance(parameter["selection_scope"], Mapping)
            or not _engineering_value_is_finite(parameter["selection_scope"])
            or not _feature_geometry_is_well_formed(parameter["feature_geometry"], primitive_ids)
            or not _dimension_definition_is_well_formed(parameter["dimension_definition"])
        ):
            return False
        parameter_ids.add(parameter_id)
    return True


def _engineering_value_is_finite(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, str):
        return True
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _engineering_value_is_finite(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_engineering_value_is_finite(item) for item in value)
    return False


def _applicable_views_are_well_formed(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_nonempty_string(view) for view in value)
        and len(value) == len(set(value))
    )


def _feature_geometry_is_well_formed(features: Any, primitive_ids: set[str]) -> bool:
    if not isinstance(features, list) or not features:
        return False
    for feature in features:
        if not isinstance(feature, Mapping):
            return False
        kind = feature.get("kind")
        primitive_id = feature.get("id")
        if (
            kind not in ENGINEERING_FEATURE_KINDS
            or not _nonempty_string(primitive_id)
            or primitive_id in primitive_ids
            or not _nonempty_string(feature.get("coordinate_system"))
            or not _engineering_value_is_finite(feature)
            or not _feature_coordinates_are_well_formed(kind, feature)
        ):
            return False
        primitive_ids.add(primitive_id)
    return True


def _feature_coordinates_are_well_formed(kind: str, feature: Mapping[str, Any]) -> bool:
    if kind == "nurbs_curve":
        return _coordinate_array(feature.get("control_points"))
    if kind == "polyline":
        return _coordinate_array(feature.get("points"))
    if kind in {"control_point", "point"}:
        return _coordinate_vector(feature.get("coordinates"))
    if kind == "local_frame":
        return all(_coordinate_vector(feature.get(field)) for field in ("origin", "s_axis", "q_axis"))
    if kind == "reference_axis":
        return all(_coordinate_vector(feature.get(field)) for field in ("origin", "direction"))
    return False


def _dimension_definition_is_well_formed(definition: Any) -> bool:
    if definition is None:
        return True
    if not isinstance(definition, Mapping):
        return False
    required_fields = {"kind", "measurement_points", "unit", "tolerance"}
    if not required_fields <= set(definition) or definition.get("kind") not in ENGINEERING_DIMENSION_KINDS:
        return False
    tolerance = definition.get("tolerance")
    return (
        _nonempty_string(definition.get("unit"))
        and _finite_number(tolerance)
        and float(tolerance) >= 0.0
        and _coordinate_array(definition.get("measurement_points"), minimum_count=2)
        and _engineering_value_is_finite(definition)
    )


def _coordinate_vector(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 2
        and all(_finite_number(coordinate) for coordinate in value)
    )


def _coordinate_array(value: Any, *, minimum_count: int = 1) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= minimum_count
        and all(_coordinate_vector(point) for point in value)
        and len({len(point) for point in value}) == 1
    )


def _engineering_parameter_records(
    canonical: Mapping[str, Any],
    blade_instances: Mapping[str, Any],
    span_stations: Mapping[str, Any],
    section_loops: Mapping[str, Any],
    resolved_dimensions: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups = [
        _parameter_group("hub", "Hub", 0),
        _parameter_group("tip_or_shroud", "Tip or Shroud", 1),
        _parameter_group("blade_placement", "Blade Placement", 2),
        _parameter_group("spanwise_pose", "Spanwise Pose", 3),
        _parameter_group("section_loop", "Section Loop", 4),
        _parameter_group("attachments", "Attachments", 5),
        _parameter_group("inspection_results", "Inspection Results", 6),
    ]
    parameters: list[dict[str, Any]] = []
    profiles = canonical.get("support_profiles", {})
    for group_id, profile_id, label in (
        ("hub", "hub_profile", "Hub profile"),
        ("tip_or_shroud", "tip_or_shroud_profile", "Tip or shroud profile"),
    ):
        profile = profiles.get(profile_id)
        if not isinstance(profile, Mapping):
            continue
        parameter_id = f"{profile_id}.curve"
        feature = copy.deepcopy(dict(profile))
        feature["id"] = f"{parameter_id}:curve"
        parameters.append(
            _inspection_parameter(
                parameter_id=parameter_id,
                group_id=group_id,
                label=label,
                requested_value=profile.get("control_points"),
                resolved_value=profile.get("control_points"),
                unit="mm",
                applicable_views=["meridional", "blade_3d"],
                feature_geometry=[feature],
                dimension_definition=None,
                selection_scope={"support_profile_id": profile_id},
                order=len(parameters),
            )
        )

    for dimension_id, label in (("main_blade_count", "Main blade count"), ("angular_pitch_deg", "Angular pitch")):
        dimension = resolved_dimensions[dimension_id]
        parameter_id = f"blade.{dimension_id}"
        parameters.append(
            _inspection_parameter(
                parameter_id=parameter_id,
                group_id="blade_placement",
                label=label,
                requested_value=dimension["requested_value"],
                resolved_value=dimension["resolved_value"],
                unit=dimension["unit"],
                applicable_views=["top", "blade_3d"],
                feature_geometry=[
                    {
                        "kind": "reference_axis",
                        "id": f"{parameter_id}:axis",
                        "coordinate_system": "xyz_mm",
                        "origin": [0.0, 0.0, 0.0],
                        "direction": [0.0, 0.0, 1.0],
                    }
                ],
                dimension_definition=None,
                selection_scope={},
                order=len(parameters),
            )
        )

    for station_id, station in span_stations.items():
        loop_id = station["section_loop_id"]
        loop = section_loops[loop_id]
        blade_id = station["blade_instance_id"]
        point = _station_reference_point(loop)
        scope = {
            "blade_instance_id": blade_id,
            "span_station_id": station_id,
            "section_loop_id": loop_id,
        }
        pose_parameter_id = f"blade:{blade_id}:station:{station_id}:pose"
        parameters.append(
            _inspection_parameter(
                parameter_id=pose_parameter_id,
                group_id="spanwise_pose",
                label="Spanwise station",
                requested_value=station.get("h"),
                resolved_value=station.get("h"),
                unit="span fraction",
                applicable_views=["s_q", "blade_3d"],
                feature_geometry=[
                    {
                        "kind": "local_frame",
                        "id": f"{pose_parameter_id}:frame",
                        "coordinate_system": "s_q_mm",
                        "origin": point,
                        "s_axis": [1.0, 0.0],
                        "q_axis": [0.0, 1.0],
                    }
                ],
                dimension_definition=None,
                selection_scope=scope,
                order=len(parameters),
            )
        )
        thickness_parameter_id = f"blade:{blade_id}:station:{station_id}:thickness"
        thickness_endpoints = _section_thickness_endpoints(loop)
        thickness_value = _distance_between_points(*thickness_endpoints)
        parameters.append(
            _inspection_parameter(
                parameter_id=thickness_parameter_id,
                group_id="section_loop",
                label="Blade thickness",
                requested_value=thickness_value,
                resolved_value=thickness_value,
                unit="mm",
                applicable_views=["s_q", "blade_3d"],
                feature_geometry=[
                    {
                        "kind": "point",
                        "id": f"{thickness_parameter_id}:pressure_point",
                        "coordinate_system": "s_q_mm",
                        "coordinates": thickness_endpoints[0],
                    },
                    {
                        "kind": "point",
                        "id": f"{thickness_parameter_id}:suction_point",
                        "coordinate_system": "s_q_mm",
                        "coordinates": thickness_endpoints[1],
                    },
                    {
                        "kind": "local_frame",
                        "id": f"{thickness_parameter_id}:frame",
                        "coordinate_system": "s_q_mm",
                        "origin": thickness_endpoints[0],
                        "s_axis": [1.0, 0.0],
                        "q_axis": [0.0, 1.0],
                    },
                ],
                dimension_definition={
                    "kind": "linear",
                    "measurement_points": thickness_endpoints,
                    "unit": "mm",
                    "tolerance": 1.0e-6,
                },
                selection_scope=scope,
                order=len(parameters),
            )
        )
        join_parameter_id = f"blade:{blade_id}:station:{station_id}:join_status"
        parameters.append(
            _inspection_parameter(
                parameter_id=join_parameter_id,
                group_id="inspection_results",
                label="Section loop continuity",
                requested_value=loop["metrics"].get("join_status"),
                resolved_value=loop["metrics"].get("join_status"),
                unit="status",
                applicable_views=["s_q", "blade_3d"],
                feature_geometry=[
                    {
                        "kind": "polyline",
                        "id": f"{join_parameter_id}:loop",
                        "coordinate_system": "s_q_mm",
                        "points": _section_loop_points(loop),
                    }
                ],
                dimension_definition=None,
                selection_scope=scope,
                order=len(parameters),
            )
        )

    root_offset = resolved_dimensions["root_offset_mm"]
    for blade_id, blade in blade_instances.items():
        station_ids = blade.get("span_station_ids", [])
        if not station_ids:
            continue
        station_id = station_ids[0]
        loop_id = span_stations[station_id]["section_loop_id"]
        parameter_id = f"blade:{blade_id}:attachment:root_offset"
        parameters.append(
            _inspection_parameter(
                parameter_id=parameter_id,
                group_id="attachments",
                label="Root offset",
                requested_value=root_offset["requested_value"],
                resolved_value=root_offset["resolved_value"],
                unit=root_offset["unit"],
                applicable_views=["meridional", "blade_3d"],
                feature_geometry=[
                    {
                        "kind": "point",
                        "id": f"{parameter_id}:point",
                        "coordinate_system": "s_q_mm",
                        "coordinates": _station_reference_point(section_loops[loop_id]),
                    }
                ],
                dimension_definition=None,
                selection_scope={
                    "blade_instance_id": blade_id,
                    "span_station_id": station_id,
                    "section_loop_id": loop_id,
                },
                order=len(parameters),
            )
        )
    return groups, parameters


def _station_reference_point(loop: Mapping[str, Any]) -> list[float]:
    pressure = loop["segment_references"]["pressure_side"]["display_points_s_q_mm"]
    return copy.deepcopy(pressure[len(pressure) // 2])


def _section_thickness_endpoints(loop: Mapping[str, Any]) -> list[list[float]]:
    pressure = loop["segment_references"]["pressure_side"]["display_points_s_q_mm"]
    suction = loop["segment_references"]["suction_side"]["display_points_s_q_mm"]
    sample_index = min(len(pressure), len(suction)) // 2
    return [copy.deepcopy(pressure[sample_index]), copy.deepcopy(suction[sample_index])]


def _distance_between_points(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((float(right_axis) - float(left_axis)) ** 2 for left_axis, right_axis in zip(left, right)))


def _section_loop_points(loop: Mapping[str, Any]) -> list[list[float]]:
    return [
        point
        for segment in loop["segment_references"].values()
        for point in segment["display_points_s_q_mm"]
    ]


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
    graph_surfaces: Mapping[str, Mapping[str, Any]],
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
        if (
            not isinstance(reference.get("quality"), Mapping)
            or not isinstance(reference.get("inspectable"), bool)
            or reference["inspectable"] != _surface_is_inspectable(graph_surfaces[surface_id])
        ):
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
        not _nonempty_string(loop.get("span_station_id"))
        or loop.get("source_coordinate_units") != {"s": "normalized", "q": "mm"}
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
        (suction[-1], trailing[0]),
        (trailing[-1], pressure[-1]),
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
    pose_controls = [
        float(point[2])
        for row in canonical.get("pose_field", {}).get("control_points", [])
        for point in row
    ]
    main_blade_count = population.get("main_blade_count")
    angular_pitch_deg = 360.0 / float(main_blade_count) if main_blade_count else None
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
        "angular_pitch_deg": _dimension(angular_pitch_deg, angular_pitch_deg, "deg"),
        "pose_theta_min_deg": _dimension(
            min(pose_controls) if pose_controls else None,
            min(pose_controls) if pose_controls else None,
            "deg",
        ),
        "pose_theta_max_deg": _dimension(
            max(pose_controls) if pose_controls else None,
            max(pose_controls) if pose_controls else None,
            "deg",
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
