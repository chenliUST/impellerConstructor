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
ENGINEERING_COORDINATE_SYSTEMS = {"model_xyz", "s_q_mm", "profile_rz_mm"}
ENGINEERING_RENDERING_ROLES = {"drawing_context", "selected_feature"}
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
        contract["parameter_groups"],
        contract["parameters"],
        blade_instances,
        span_stations,
        section_loops,
        support_profiles,
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
    if has_parameters:
        if any(
            not _selection_scope_is_valid(
                parameter["selection_scope"],
                blade_instances,
                span_stations,
                section_loops,
                support_profiles,
            )
            for parameter in contract["parameters"]
        ):
            failures.append({"reason": "parameter_inspection_contract_unsupported"})
        measurement_failures = _validate_engineering_parameters(contract["parameters"])
        if not failures and not measurement_failures and not _engineering_parameters_match_source_geometry(
            surface_graph,
            contract["parameters"],
            span_stations,
            section_loops,
            surface_graph.get("canonical_nurbs_parameterization", {}).get("support_profiles", {}),
        ):
            failures.append({"reason": "parameter_inspection_contract_unsupported"})
        failures.extend(measurement_failures)
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
                source_points_xyz = copy.deepcopy(segment.get("points_xyz", []))
                source_controls = copy.deepcopy(segment.get("control_points_s_q", []))
                segment_references[name] = {
                    "section_segment_id": segment_id,
                    "source_segment_name": name,
                    "points_s_q": source_points,
                    "points_xyz": source_points_xyz,
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
        surface_graph,
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
        "feature_geometry": [_normalized_feature_geometry(feature) for feature in feature_geometry],
        "dimension_definition": copy.deepcopy(dimension_definition),
        "selection_scope": copy.deepcopy(dict(selection_scope)),
        "order": order,
    }


def _normalized_feature_geometry(feature: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(feature))
    normalized["coordinate_system"] = {
        "xyz_mm": "model_xyz",
        "xy_mm": "model_xyz",
        "rz_meridional_mm": "profile_rz_mm",
    }.get(normalized.get("coordinate_system"), normalized.get("coordinate_system"))
    normalized.setdefault("rendering_role", "selected_feature")
    return normalized


def _engineering_records_are_well_formed(
    parameter_groups: Any,
    parameters: Any,
    blade_instances: Mapping[str, Any],
    span_stations: Mapping[str, Any],
    section_loops: Mapping[str, Any],
    support_profiles: Mapping[str, Any],
) -> bool:
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
            or not _feature_geometry_is_well_formed(
                parameter["feature_geometry"], primitive_ids, parameter["applicable_views"]
            )
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


def _feature_geometry_is_well_formed(
    features: Any, primitive_ids: set[str], applicable_views: Sequence[str]
) -> bool:
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
            or feature.get("coordinate_system") not in ENGINEERING_COORDINATE_SYSTEMS
            or feature.get("rendering_role") not in ENGINEERING_RENDERING_ROLES
            or not _engineering_value_is_finite(feature)
            or not _feature_coordinates_are_well_formed(kind, feature)
            or not _feature_coordinate_dimension_is_valid(kind, feature)
            or not all(_feature_supports_view(feature, view) for view in applicable_views)
        ):
            return False
        primitive_ids.add(primitive_id)
    return True


def _feature_coordinate_dimension_is_valid(kind: str, feature: Mapping[str, Any]) -> bool:
    expected = 3 if feature.get("coordinate_system") == "model_xyz" else 2
    if kind == "nurbs_curve":
        return all(len(point) == expected for point in feature["control_points"])
    if kind == "polyline":
        return all(len(point) == expected for point in feature["points"])
    if kind in {"control_point", "point"}:
        return len(feature["coordinates"]) == expected
    if kind == "local_frame":
        return all(len(feature[field]) == expected for field in ("origin", "s_axis", "q_axis"))
    if kind == "reference_axis":
        return all(len(feature[field]) == expected for field in ("origin", "direction"))
    return False


def _feature_supports_view(feature: Mapping[str, Any], view: str) -> bool:
    coordinate_system = feature.get("coordinate_system")
    if view in {"blade_3d", "top"}:
        return coordinate_system == "model_xyz"
    if view == "meridional":
        return coordinate_system in {"model_xyz", "profile_rz_mm"}
    if view != "s_q":
        return False
    if coordinate_system == "s_q_mm":
        return True
    display_fields = {
        "nurbs_curve": ("display_control_points_s_q_mm",),
        "polyline": ("display_points_s_q_mm",),
        "control_point": ("display_coordinates_s_q_mm",),
        "point": ("display_coordinates_s_q_mm",),
        "local_frame": ("display_origin_s_q_mm", "display_s_axis_s_q_mm", "display_q_axis_s_q_mm"),
        "reference_axis": ("display_origin_s_q_mm", "display_direction_s_q_mm"),
    }.get(feature.get("kind"), ())
    return bool(display_fields) and all(field in feature for field in display_fields)


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
    if not (
        _nonempty_string(definition.get("unit"))
        and _finite_number(tolerance)
        and float(tolerance) >= 0.0
        and _coordinate_array(definition.get("measurement_points"), minimum_count=2)
        and _engineering_value_is_finite(definition)
    ):
        return False
    kind = definition["kind"]
    points = definition["measurement_points"]
    if kind == "angular":
        return (
            _coordinate_vector(definition.get("reference_direction"))
            and _coordinate_vector(definition.get("measured_direction"))
            and len(definition["reference_direction"]) == len(definition["measured_direction"])
            and _vector_norm(definition["reference_direction"]) > 1.0e-9
            and _vector_norm(definition["measured_direction"]) > 1.0e-9
        )
    if kind == "arc_height":
        return len(points) >= 3 and _distance(points[0], points[1]) > 1.0e-9
    if kind != "control_coordinate":
        return _distance(points[0], points[1]) > 1.0e-9
    return True


def _selection_scope_is_valid(
    scope: Mapping[str, Any],
    blade_instances: Mapping[str, Any],
    span_stations: Mapping[str, Any],
    section_loops: Mapping[str, Any],
    support_profiles: Mapping[str, Any],
) -> bool:
    profile_id = scope.get("support_profile_id")
    if profile_id is not None and profile_id not in support_profiles:
        return False
    blade_id = scope.get("blade_instance_id")
    if blade_id is not None and blade_id not in blade_instances:
        return False
    station_id = scope.get("span_station_id")
    if station_id is not None:
        station = span_stations.get(station_id)
        if station is None or (blade_id is not None and station.get("blade_instance_id") != blade_id):
            return False
    loop_id = scope.get("section_loop_id")
    if loop_id is not None:
        loop = section_loops.get(loop_id)
        if loop is None or (station_id is not None and loop.get("span_station_id") != station_id):
            return False
    segment_id = scope.get("section_segment_id")
    if segment_id is not None:
        if loop_id is None:
            return False
        segment = next(
            (
                record
                for record in section_loops[loop_id].get("segment_references", {}).values()
                if record.get("section_segment_id") == segment_id
            ),
            None,
        )
        if segment is None:
            return False
        source_control_point_id = scope.get("source_control_point_id")
        if source_control_point_id is not None and not any(
            record.get("control_point_id") == source_control_point_id
            for record in segment.get("control_points", [])
        ):
            return False
    return True


def _engineering_parameters_match_source_geometry(
    surface_graph: Mapping[str, Any],
    parameters: Sequence[Mapping[str, Any]],
    span_stations: Mapping[str, Any],
    section_loops: Mapping[str, Any],
    support_profiles: Mapping[str, Any],
) -> bool:
    surfaces = {
        surface.get("id"): surface
        for surface in surface_graph.get("surfaces", [])
        if isinstance(surface, Mapping) and _nonempty_string(surface.get("id"))
    }
    for parameter in parameters:
        scope = parameter["selection_scope"]
        parameter_id = parameter["parameter_id"]
        if not _selection_scope_identity_matches(parameter, surface_graph):
            return False
        source_control_point_id = scope.get("source_control_point_id")
        if source_control_point_id is not None and not _section_control_matches_source(
            parameter, scope, surface_graph
        ):
            return False
        if "source_profile_control_index" in scope and not _profile_control_matches_source(
            parameter, scope, support_profiles
        ):
            return False
        if "source_canonical_path" in scope and not _canonical_parameter_matches_source(
            parameter, scope, surface_graph
        ):
            return False
        if parameter_id.endswith(".profile.degree") and not _profile_curve_matches_source(
            parameter, scope, support_profiles
        ):
            return False
        if parameter_id.endswith(".curve") and not _profile_curve_matches_source(
            parameter, scope, support_profiles
        ):
            return False
        if (":pose.station." in parameter_id or parameter_id.endswith(":pose")) and not _station_parameter_matches_source(
            parameter, scope, surface_graph
        ):
            return False
        if parameter_id.endswith(":thickness") and not _thickness_parameter_matches_source(
            parameter, scope, surface_graph
        ):
            return False
        if ":sagitta" in parameter_id and not _sagitta_parameter_matches_source(
            parameter, scope, surface_graph
        ):
            return False
        if "source_attachment_measurement" in scope and not _attachment_parameter_matches_source(
            parameter, scope, surfaces
        ):
            return False
        if parameter_id in {
            "blade.main.count",
            "blade.angular_pitch",
            "blade.splitter.phase",
            "blade.main_blade_count",
            "blade.angular_pitch_deg",
        } and not _placement_parameter_matches_source(
            parameter, surface_graph
        ):
            return False
        if parameter_id == "shroud.thickness" and not _shroud_thickness_matches_source(parameter, surfaces):
            return False
        if parameter_id.endswith("join_status") and not _join_status_matches_source(parameter, scope, surface_graph):
            return False
        if "source_join_metric" in scope and not _loop_join_parameter_matches_source(
            parameter, scope, surface_graph
        ):
            return False
        if parameter_id.endswith("root_offset") and not _root_offset_matches_source(parameter, scope, surface_graph):
            return False
    return True


def _canonical_parameter_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], surface_graph: Mapping[str, Any]
) -> bool:
    value: Any = surface_graph.get("canonical_nurbs_parameterization", {})
    path = scope.get("source_canonical_path")
    if not isinstance(path, list) or not path:
        return False
    try:
        for part in path:
            value = value[part] if isinstance(part, int) else value[str(part)]
    except (KeyError, IndexError, TypeError):
        return False
    return parameter.get("requested_value") == value and parameter.get("resolved_value") == value


def _loop_join_parameter_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], surface_graph: Mapping[str, Any]
) -> bool:
    loop = _generated_loop(surface_graph, scope)
    join_name = scope.get("source_join_name")
    metric_name = scope.get("source_join_metric")
    if loop is None or not isinstance(join_name, str) or not isinstance(metric_name, str):
        return False
    value = loop.get("join_metrics", {}).get(join_name, {}).get(metric_name)
    return parameter.get("requested_value") == value and parameter.get("resolved_value") == value


def _selected_feature_geometry(parameter: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        feature
        for feature in parameter.get("feature_geometry", [])
        if feature.get("rendering_role") == "selected_feature"
    ]


def _selection_scope_identity_matches(parameter: Mapping[str, Any], surface_graph: Mapping[str, Any]) -> bool:
    scope = parameter["selection_scope"]
    if "source_station_index" not in scope:
        return True
    loop = _generated_loop(surface_graph, scope)
    blade_id = scope.get("blade_instance_id")
    station_index = scope.get("source_station_index")
    if loop is None or not isinstance(blade_id, str) or not isinstance(station_index, int):
        return False
    station_id = f"{blade_id}:span_{station_index}"
    loop_id = f"{station_id}:loop"
    if scope.get("span_station_id") != station_id or scope.get("section_loop_id") != loop_id:
        return False
    segment_name = scope.get("source_segment_name")
    if segment_name is None:
        return True
    segment = loop.get("segments", {}).get(segment_name)
    if not isinstance(segment, Mapping) or scope.get("section_segment_id") != f"{loop_id}:{segment_name}":
        return False
    control_index = scope.get("source_control_index")
    if control_index is None:
        return True
    controls = segment.get("control_points_s_q", [])
    if not isinstance(control_index, int) or control_index < 0 or control_index >= len(controls):
        return False
    scale = loop.get("streamwise_metric_scale_mm")
    if not _finite_number(scale):
        return False
    expected_control_id = _control_point_records(f"{loop_id}:{segment_name}", controls, float(scale))[control_index][
        "control_point_id"
    ]
    if scope.get("source_control_point_id") != expected_control_id:
        return False
    axis = parameter["parameter_id"].rsplit(":", 1)[-1]
    return parameter["parameter_id"] == (
        f"blade:{blade_id}:station:{station_id}:section:{segment_name}:control:{control_index}:{axis}"
    )


def _section_control_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], surface_graph: Mapping[str, Any]
) -> bool:
    loop = _generated_loop(surface_graph, scope)
    if loop is None:
        return False
    segment = loop.get("segments", {}).get(scope.get("source_segment_name"))
    metric_scale = loop.get("streamwise_metric_scale_mm")
    if not isinstance(segment, Mapping) or not _finite_number(metric_scale):
        return False
    index = scope.get("source_control_index")
    controls = segment.get("control_points_s_q", [])
    if not isinstance(index, int) or index < 0 or index >= len(controls):
        return False
    source_coordinates = controls[index]
    coordinates = _metric_s_q_points([source_coordinates], float(metric_scale))[0]
    axis_index = 0 if parameter["parameter_id"].endswith(":s") else 1
    feature = parameter["feature_geometry"]
    return (
        len(feature) == 1
        and feature[0].get("kind") == "control_point"
        and feature[0].get("coordinates") == coordinates
        and parameter["dimension_definition"] == _coordinate_dimension(coordinates, axis_index, "mm")
        and parameter["resolved_value"] == abs(float(coordinates[axis_index]))
    )


def _profile_control_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], support_profiles: Mapping[str, Any]
) -> bool:
    profile_id = scope.get("source_profile_id")
    if profile_id != scope.get("support_profile_id"):
        return False
    profile = support_profiles.get(profile_id)
    index = scope.get("source_profile_control_index")
    if not isinstance(index, int) or profile is None or index < 0 or index >= len(profile.get("control_points", [])):
        return False
    coordinates = profile["control_points"][index]
    axis_index = 0 if parameter["parameter_id"].endswith(".r") else 1
    feature = _selected_feature_geometry(parameter)
    prefix = "hub.profile" if profile_id == "hub_profile" else "tip_or_shroud.profile"
    return (
        parameter["group_id"] == ("hub" if profile_id == "hub_profile" else "tip_or_shroud")
        and parameter["parameter_id"] == f"{prefix}.control.{index}.{'r' if axis_index == 0 else 'z'}"
        and len(feature) == 1
        and feature[0].get("kind") == "control_point"
        and feature[0].get("coordinates") == coordinates
        and parameter["dimension_definition"] == _coordinate_dimension(coordinates, axis_index, "mm")
        and parameter["resolved_value"] == abs(float(coordinates[axis_index]))
    )


def _profile_curve_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], support_profiles: Mapping[str, Any]
) -> bool:
    profile_id = scope.get("source_profile_id")
    if profile_id != scope.get("support_profile_id"):
        return False
    profile = support_profiles.get(profile_id)
    features = parameter["feature_geometry"]
    prefix = "hub.profile" if profile_id == "hub_profile" else "tip_or_shroud.profile"
    is_degree = parameter["parameter_id"] == f"{prefix}.degree"
    is_legacy_curve = parameter["parameter_id"] == f"{profile_id}.curve"
    return (
        profile is not None
        and (is_degree or is_legacy_curve)
        and parameter["group_id"] == ("hub" if profile_id == "hub_profile" else "tip_or_shroud")
        and len(features) == 1
        and features[0].get("kind") == "nurbs_curve"
        and features[0].get("id") == f"{parameter['parameter_id']}:curve"
        and features[0].get("degree") == profile.get("degree")
        and features[0].get("control_points") == profile.get("control_points")
        and parameter["resolved_value"] == (profile.get("degree") if is_degree else profile.get("control_points"))
    )


def _station_parameter_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], surface_graph: Mapping[str, Any]
) -> bool:
    loop = _generated_loop(surface_graph, scope)
    features = parameter["feature_geometry"]
    return (
        loop is not None
        and parameter["resolved_value"] == loop.get("h")
        and len(features) == 1
        and features[0].get("kind") == "local_frame"
        and features[0].get("origin") == _generated_station_reference_point(loop)
    )


def _thickness_parameter_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], surface_graph: Mapping[str, Any]
) -> bool:
    loop = _generated_loop(surface_graph, scope)
    if loop is None:
        return False
    scale = loop.get("streamwise_metric_scale_mm")
    if not _finite_number(scale):
        return False
    pressure = _metric_s_q_points(loop["segments"]["pressure_side"]["points_s_q"], float(scale))
    suction = _metric_s_q_points(loop["segments"]["suction_side"]["points_s_q"], float(scale))
    pressure_xyz = loop["segments"]["pressure_side"]["points_xyz"]
    suction_xyz = loop["segments"]["suction_side"]["points_xyz"]
    sample_index = min(len(pressure), len(suction)) // 2
    endpoints = [pressure[sample_index], suction[sample_index]]
    endpoints_xyz = [pressure_xyz[sample_index], suction_xyz[sample_index]]
    point_features = [feature for feature in _selected_feature_geometry(parameter) if feature.get("kind") == "point"]
    return (
        [feature.get("coordinates") for feature in point_features] == endpoints_xyz
        and [feature.get("display_coordinates_s_q_mm") for feature in point_features] == endpoints
        and parameter["dimension_definition"].get("measurement_points") == endpoints
        and parameter["resolved_value"] == _distance(*endpoints)
    )


def _sagitta_parameter_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], surface_graph: Mapping[str, Any]
) -> bool:
    loop = _generated_loop(surface_graph, scope)
    if loop is None or not _finite_number(loop.get("streamwise_metric_scale_mm")):
        return False
    segment = loop.get("segments", {}).get(scope.get("source_segment_name"))
    if not isinstance(segment, Mapping):
        return False
    points = _metric_s_q_points(segment["points_s_q"], float(loop["streamwise_metric_scale_mm"]))
    points_xyz = segment["points_xyz"]
    expected = [points[0], points[-1], points[len(points) // 2]]
    measurement_features = [
        feature
        for feature in parameter["feature_geometry"]
        if feature.get("kind") == "point" and feature.get("rendering_role") == "selected_feature"
    ]
    return (
        parameter["feature_geometry"][0].get("points") == points_xyz
        and parameter["feature_geometry"][0].get("kind") == "polyline"
        and parameter["feature_geometry"][0].get("display_points_s_q_mm") == points
        and measurement_features == _sagitta_measurement_features(parameter["parameter_id"], points_xyz, points)
        and parameter["dimension_definition"].get("measurement_points") == expected
        and parameter["resolved_value"] == _point_line_distance(expected[2], expected[0], expected[1])
    )


def _generated_loop(surface_graph: Mapping[str, Any], scope: Mapping[str, Any]) -> Mapping[str, Any] | None:
    blade_id = scope.get("blade_instance_id")
    station_index = scope.get("source_station_index")
    if not isinstance(blade_id, str) or not blade_id.startswith("blade_") or not isinstance(station_index, int):
        return None
    try:
        blade_index = int(blade_id.removeprefix("blade_"))
        return surface_graph["blade_to_blade_loop_family"]["blades"][blade_index]["loops"][station_index]
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _generated_station_reference_point(loop: Mapping[str, Any]) -> list[float]:
    scale = loop.get("streamwise_metric_scale_mm")
    pressure = loop.get("segments", {}).get("pressure_side", {}).get("points_s_q", [])
    if not _finite_number(scale) or not pressure:
        return []
    return _metric_s_q_points(pressure, float(scale))[len(pressure) // 2]


def _generated_station_reference_point_xyz(loop: Mapping[str, Any]) -> list[float]:
    pressure = loop.get("segments", {}).get("pressure_side", {}).get("points_xyz", [])
    return copy.deepcopy(pressure[len(pressure) // 2]) if pressure else []


def _placement_parameter_matches_source(parameter: Mapping[str, Any], surface_graph: Mapping[str, Any]) -> bool:
    blades = surface_graph.get("blade_to_blade_loop_family", {}).get("blades", [])
    main_count = sum(1 for blade in blades if blade.get("blade_class") == "main")
    main_directions = _graph_blade_anchor_directions(surface_graph, "main")
    splitter_directions = _graph_blade_anchor_directions(surface_graph, "splitter")
    parameter_id = parameter["parameter_id"]
    if parameter_id == "blade.main_blade_count":
        feature = _selected_feature_geometry(parameter)
        return (
            parameter["resolved_value"] == main_count
            and parameter["selection_scope"].get("source_geometry_kind") == "blade_population"
            and len(feature) == 1
            and feature[0].get("kind") == "reference_axis"
            and feature[0].get("origin") == [0.0, 0.0, 0.0]
            and feature[0].get("direction") == [0.0, 0.0, 1.0]
        )
    if parameter_id == "blade.angular_pitch_deg":
        expected = _angle_degrees(main_directions[0], main_directions[1]) if len(main_directions) >= 2 else None
        feature = _selected_feature_geometry(parameter)
        return (
            expected is not None
            and math.isclose(float(parameter["resolved_value"]), expected, rel_tol=0.0, abs_tol=1.0e-9)
            and parameter["selection_scope"].get("source_geometry_kind") == "blade_placement"
            and len(feature) == 1
            and feature[0].get("kind") == "reference_axis"
            and feature[0].get("origin") == [0.0, 0.0, 0.0]
            and feature[0].get("direction") == [0.0, 0.0, 1.0]
        )
    if parameter_id == "blade.main.count":
        feature = _selected_feature_geometry(parameter)
        context = [
            item for item in parameter["feature_geometry"] if item.get("rendering_role") == "drawing_context"
        ]
        return (
            parameter["resolved_value"] == main_count
            and parameter["selection_scope"].get("source_geometry_kind") == "blade_population"
            and len(feature) == 1
            and feature[0].get("kind") == "reference_axis"
            and feature[0].get("origin") == [0.0, 0.0, 0.0]
            and feature[0].get("direction") == [1.0, 0.0, 0.0]
            and context == _top_context_features(surface_graph)
        )
    if parameter_id == "blade.angular_pitch":
        expected = _angular_dimension(main_directions[0], main_directions[1]) if len(main_directions) >= 2 else None
        feature = _selected_feature_geometry(parameter)
        return (
            expected is not None
            and parameter["dimension_definition"] == expected
            and parameter["resolved_value"] == _measure_dimension(expected)
            and len(feature) == 2
            and [item.get("direction") for item in feature] == [
                [*main_directions[0], 0.0],
                [*main_directions[1], 0.0],
            ]
        )
    if parameter_id == "blade.splitter.phase":
        if main_directions and splitter_directions:
            expected = _angular_dimension(main_directions[0], splitter_directions[0])
            feature = _selected_feature_geometry(parameter)
            return (
                parameter["dimension_definition"] == expected
                and parameter["resolved_value"] == _measure_dimension(expected)
                and len(feature) == 1
                and feature[0].get("direction") == [*main_directions[0], 0.0]
            )
        feature = _selected_feature_geometry(parameter)
        return parameter["resolved_value"] == "not_applicable" and feature[0].get("direction") == [1.0, 0.0, 0.0]
    return False


def _graph_blade_anchor_directions(surface_graph: Mapping[str, Any], blade_class: str) -> list[list[float]]:
    blades = surface_graph.get("blade_to_blade_loop_family", {}).get("blades", [])
    surfaces = {surface.get("id"): surface for surface in surface_graph.get("surfaces", []) if isinstance(surface, Mapping)}
    directions: list[list[float]] = []
    for blade_index, blade in enumerate(blades):
        if blade.get("blade_class") != blade_class:
            continue
        surface = surfaces.get(f"blade_{blade_index}_root_attachment_surface")
        point = surface.get("uv_grid", [[None]])[-1][0] if surface else None
        if _coordinate_vector(point) and len(point) >= 3:
            directions.append([float(point[0]), float(point[1])])
    return directions


def _shroud_thickness_matches_source(parameter: Mapping[str, Any], surfaces: Mapping[str, Mapping[str, Any]]) -> bool:
    inner = surfaces.get(parameter["selection_scope"].get("source_shroud_inner_surface_id"))
    outer = surfaces.get(parameter["selection_scope"].get("source_shroud_outer_surface_id"))
    if inner is None or outer is None:
        return False
    points = [inner.get("uv_grid", [[None]])[0][0], outer.get("uv_grid", [[None]])[0][0]]
    features = [feature.get("coordinates") for feature in parameter["feature_geometry"] if feature.get("kind") == "point"]
    return (
        all(_coordinate_vector(point) for point in points)
        and features == points
        and parameter["dimension_definition"].get("measurement_points") == points
        and parameter["resolved_value"] == _distance(*points)
    )


def _join_status_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], surface_graph: Mapping[str, Any]
) -> bool:
    loop = _generated_loop(surface_graph, scope)
    if loop is None:
        return False
    scale = loop.get("streamwise_metric_scale_mm")
    if not _finite_number(scale):
        return False
    points = [
        point
        for segment in loop.get("segments", {}).values()
        for point in _metric_s_q_points(segment.get("points_s_q", []), float(scale))
    ]
    points_xyz = [
        point
        for segment in loop.get("segments", {}).values()
        for point in segment.get("points_xyz", [])
    ]
    feature = parameter["feature_geometry"]
    return (
        parameter["resolved_value"] == loop.get("metrics", {}).get("join_status")
        and len(feature) == 1
        and feature[0].get("kind") == "polyline"
        and feature[0].get("points") == points_xyz
        and feature[0].get("display_points_s_q_mm") == points
    )


def _root_offset_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], surface_graph: Mapping[str, Any]
) -> bool:
    loop = _generated_loop(surface_graph, scope)
    resolved = (
        surface_graph.get("canonical_nurbs_parameterization", {})
        .get("active_span_policy", {})
        .get("root_offset", {})
        .get("resolved_constant_mm")
    )
    feature = parameter["feature_geometry"]
    return (
        loop is not None
        and parameter["resolved_value"] == resolved
        and len(feature) == 1
        and feature[0].get("kind") == "point"
        and feature[0].get("coordinates") == _generated_station_reference_point_xyz(loop)
        and feature[0].get("display_coordinates_s_q_mm") == _generated_station_reference_point(loop)
    )


def _attachment_parameter_matches_source(
    parameter: Mapping[str, Any], scope: Mapping[str, Any], surfaces: Mapping[str, Mapping[str, Any]]
) -> bool:
    surface = surfaces.get(scope.get("source_attachment_surface_id"))
    blade_id = scope.get("blade_instance_id")
    measurement = scope.get("source_attachment_measurement")
    if not isinstance(blade_id, str) or not isinstance(measurement, str) or surface is None:
        return False
    attachment = "root" if measurement.startswith("root_") else "shroud"
    expected_surface_id = (
        f"{blade_id}_root_attachment_surface"
        if attachment == "root"
        else f"{blade_id}_closed_shroud_attachment_surface"
    )
    if surface.get("id") != expected_surface_id or parameter["parameter_id"] != (
        f"blade:{blade_id}:attachment:{attachment}:{measurement.split('_', 1)[1]}"
    ):
        return False
    points = _attachment_measurement_points(surface, scope.get("source_attachment_measurement")) if surface else None
    model_points = _attachment_model_measurement_points(surface, measurement)
    prefix = parameter["parameter_id"]
    expected_context = _attachment_context_features(prefix, surface, attachment)
    context = [
        feature
        for feature in parameter["feature_geometry"]
        if feature.get("rendering_role") == "drawing_context"
    ]
    features = [
        feature.get("coordinates")
        for feature in _selected_feature_geometry(parameter)
        if feature.get("kind") == "point"
    ]
    return (
        points is not None
        and model_points is not None
        and context == expected_context
        and features == model_points
        and parameter["dimension_definition"].get("measurement_points") == points
        and parameter["resolved_value"] == _distance(*points)
    )


def _attachment_measurement_points(surface: Mapping[str, Any], measurement: Any) -> list[list[float]] | None:
    if measurement == "root_width":
        domain = surface.get("v1_1_root_domain_samples", {})
        quality = surface.get("v1_1_root_quality", {})
        scale = quality.get("root_streamwise_metric_scale_mm")
        if _finite_number(scale):
            return _metric_s_q_points([domain["hub_outer_loop_s_q"][0], domain["blade_inner_loop_s_q"][0]], float(scale))
    if measurement == "root_lift":
        rows = surface.get("uv_grid", [])
        if rows and rows[0] and rows[-1]:
            return [copy.deepcopy(rows[0][0]), copy.deepcopy(rows[-1][0])]
    if measurement == "shroud_width":
        edges = surface.get("edge_samples", {})
        return [copy.deepcopy(edges["shroud_reference_loop"][0]), copy.deepcopy(edges["shroud_attachment_loop"][0])]
    if measurement == "shroud_lift":
        edges = surface.get("edge_samples", {})
        return [copy.deepcopy(edges["blade_tip_loop"][0]), copy.deepcopy(edges["shroud_reference_loop"][0])]
    return None


def _attachment_model_measurement_points(
    surface: Mapping[str, Any], measurement: Any
) -> list[list[float]] | None:
    edges = surface.get("edge_samples", {})
    if measurement == "root_width":
        return [copy.deepcopy(edges["hub_outer_loop"][0]), copy.deepcopy(edges["blade_inner_loop"][0])]
    return _attachment_measurement_points(surface, measurement)


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


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(
        sum((float(right_axis) - float(left_axis)) ** 2 for left_axis, right_axis in zip(left, right))
    )


def _vector_norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(float(axis) ** 2 for axis in vector))


def _angle_degrees(reference_direction: Sequence[float], measured_direction: Sequence[float]) -> float:
    denominator = _vector_norm(reference_direction) * _vector_norm(measured_direction)
    if denominator <= 1.0e-9:
        raise ValueError("parameter_inspection_dimension_degenerate")
    cosine = sum(
        float(reference_axis) * float(measured_axis)
        for reference_axis, measured_axis in zip(reference_direction, measured_direction)
    ) / denominator
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _point_line_distance(point: Sequence[float], start: Sequence[float], end: Sequence[float]) -> float:
    baseline = [float(right) - float(left) for left, right in zip(start, end)]
    baseline_length = _vector_norm(baseline)
    if baseline_length <= 1.0e-9:
        raise ValueError("parameter_inspection_dimension_degenerate")
    offset = [float(coordinate) - float(origin) for coordinate, origin in zip(point, start)]
    projection = sum(component * direction for component, direction in zip(offset, baseline)) / baseline_length
    perpendicular = [component - projection * direction / baseline_length for component, direction in zip(offset, baseline)]
    return _vector_norm(perpendicular)


def _measure_dimension(definition: Mapping[str, Any]) -> float:
    kind = definition["kind"]
    points = definition["measurement_points"]
    if kind in {"linear", "radial", "diameter", "ordinate", "control_coordinate"}:
        return _distance(points[0], points[1]) * (2.0 if kind == "diameter" else 1.0)
    if kind == "angular":
        return _angle_degrees(definition["reference_direction"], definition["measured_direction"])
    if kind == "arc_height":
        return _point_line_distance(points[2], points[0], points[1])
    raise ValueError("parameter_inspection_dimension_kind_unsupported")


def _validate_engineering_parameters(parameters: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for parameter in parameters:
        parameter_id = parameter.get("parameter_id")
        if not isinstance(parameter_id, str) or not parameter_id or parameter_id in seen:
            failures.append(
                {"reason": "parameter_inspection_parameter_id_invalid", "parameter_id": parameter_id}
            )
            continue
        seen.add(parameter_id)
        definition = parameter.get("dimension_definition")
        if definition is not None:
            measured = _measure_dimension(definition)
            tolerance = float(definition.get("tolerance", 1.0e-6))
            if abs(measured - float(parameter["resolved_value"])) > tolerance:
                failures.append(
                    {
                        "reason": "parameter_inspection_dimension_value_mismatch",
                        "parameter_id": parameter_id,
                    }
                )
    return failures


def _engineering_parameter_records(
    surface_graph: Mapping[str, Any],
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
        feature["rendering_role"] = "drawing_context"
        parameters.append(
            _inspection_parameter(
                parameter_id=parameter_id,
                group_id=group_id,
                label=label,
                requested_value=profile.get("control_points"),
                resolved_value=profile.get("control_points"),
                unit="mm",
                applicable_views=["meridional"],
                feature_geometry=[feature],
                dimension_definition=None,
                selection_scope={"support_profile_id": profile_id, "source_profile_id": profile_id},
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
                selection_scope={"source_geometry_kind": "blade_population" if dimension_id == "main_blade_count" else "blade_placement"},
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
            "source_station_index": station["source_loop_index"],
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
                applicable_views=["s_q"],
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
        thickness_endpoints_xyz = _section_thickness_endpoints_xyz(loop)
        thickness_frame = _section_thickness_frame(loop)
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
                    *_section_context_features(thickness_parameter_id, loop),
                    {
                        "kind": "point",
                        "id": f"{thickness_parameter_id}:pressure_point",
                        "coordinate_system": "model_xyz",
                        "coordinates": thickness_endpoints_xyz[0],
                        "display_coordinates_s_q_mm": thickness_endpoints[0],
                    },
                    {
                        "kind": "point",
                        "id": f"{thickness_parameter_id}:suction_point",
                        "coordinate_system": "model_xyz",
                        "coordinates": thickness_endpoints_xyz[1],
                        "display_coordinates_s_q_mm": thickness_endpoints[1],
                    },
                    {
                        "kind": "local_frame",
                        "id": f"{thickness_parameter_id}:frame",
                        "coordinate_system": "model_xyz",
                        **thickness_frame,
                        "display_origin_s_q_mm": thickness_endpoints[0],
                        "display_s_axis_s_q_mm": [1.0, 0.0],
                        "display_q_axis_s_q_mm": [0.0, 1.0],
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
                        "coordinate_system": "model_xyz",
                        "points": _section_loop_points_xyz(loop),
                        "display_points_s_q_mm": _section_loop_points(loop),
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
                        "coordinate_system": "model_xyz",
                        "coordinates": _station_reference_point_xyz(section_loops[loop_id]),
                        "display_coordinates_s_q_mm": _station_reference_point(section_loops[loop_id]),
                    }
                ],
                dimension_definition=None,
                selection_scope={
                    "blade_instance_id": blade_id,
                    "span_station_id": station_id,
                    "section_loop_id": loop_id,
                    "source_station_index": span_stations[station_id]["source_loop_index"],
                },
                order=len(parameters),
            )
        )
    _append_complete_engineering_parameters(
        parameters,
        surface_graph,
        canonical,
        blade_instances,
        span_stations,
        section_loops,
    )
    return groups, parameters


def _append_complete_engineering_parameters(
    parameters: list[dict[str, Any]],
    surface_graph: Mapping[str, Any],
    canonical: Mapping[str, Any],
    blade_instances: Mapping[str, Any],
    span_stations: Mapping[str, Any],
    section_loops: Mapping[str, Any],
) -> None:
    def append(**kwargs: Any) -> None:
        parameters.append(_inspection_parameter(order=len(parameters), **kwargs))

    profiles = canonical.get("support_profiles", {})
    for profile_key, profile_id, group_id, prefix, label in (
        ("hub_profile", "hub_profile", "hub", "hub.profile", "Hub profile"),
        (
            "tip_or_shroud_profile",
            "tip_or_shroud_profile",
            "tip_or_shroud",
            "tip_or_shroud.profile",
            "Tip or shroud profile",
        ),
    ):
        profile = profiles.get(profile_key)
        if not isinstance(profile, Mapping):
            continue
        curve = copy.deepcopy(dict(profile))
        curve["id"] = f"{prefix}.degree:curve"
        curve["rendering_role"] = "drawing_context"
        append(
            parameter_id=f"{prefix}.degree",
            group_id=group_id,
            label=f"{label} degree",
            requested_value=profile.get("degree"),
            resolved_value=profile.get("degree"),
            unit="degree",
            applicable_views=["meridional"],
            feature_geometry=[curve],
            dimension_definition=None,
            selection_scope={"support_profile_id": profile_id, "source_profile_id": profile_id},
        )
        for index, point in enumerate(profile.get("control_points", [])):
            if not _coordinate_vector(point):
                continue
            for axis, axis_index in (("r", 0), ("z", 1)):
                parameter_id = f"{prefix}.control.{index}.{axis}"
                context_curve = copy.deepcopy(dict(profile))
                context_curve["id"] = f"{parameter_id}:profile_context"
                context_curve["rendering_role"] = "drawing_context"
                append(
                    parameter_id=parameter_id,
                    group_id=group_id,
                    label=f"{label} control {index} {axis}",
                    requested_value=point[axis_index],
                    resolved_value=abs(float(point[axis_index])),
                    unit="mm",
                    applicable_views=["meridional"],
                    feature_geometry=[
                        context_curve,
                        {
                            "kind": "control_point",
                            "id": f"{parameter_id}:control_point",
                            "coordinate_system": "rz_meridional_mm",
                            "coordinates": copy.deepcopy(point),
                        }
                    ],
                    dimension_definition=_coordinate_dimension(point, axis_index, "mm"),
                    selection_scope={
                        "support_profile_id": profile_id,
                        "source_profile_id": profile_id,
                        "source_profile_control_index": index,
                    },
                )

        for field_name, unit in (("knots", "knot"), ("weights", "weight")):
            values = profile.get(field_name)
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                append(
                    parameter_id=f"{prefix}.{field_name}.{index}",
                    group_id=group_id,
                    label=f"{label} {field_name[:-1]} {index}",
                    requested_value=value,
                    resolved_value=value,
                    unit=unit,
                    applicable_views=["meridional"],
                    feature_geometry=[{
                        **copy.deepcopy(dict(profile)),
                        "id": f"{prefix}.{field_name}.{index}:curve",
                        "rendering_role": "selected_feature",
                    }],
                    dimension_definition=None,
                    selection_scope={
                        "support_profile_id": profile_id,
                        "source_profile_id": profile_id,
                        "source_canonical_path": ["support_profiles", profile_key, field_name, index],
                    },
                )

    _append_canonical_field_parameters(parameters, canonical)

    surface_by_id = {
        surface.get("id"): surface
        for surface in surface_graph.get("surfaces", [])
        if isinstance(surface, Mapping) and _nonempty_string(surface.get("id"))
    }
    main_directions = _blade_anchor_directions(blade_instances, surface_by_id, "main")
    append(
        parameter_id="blade.main.count",
        group_id="blade_placement",
        label="Main blade count",
        requested_value=len(main_directions),
        resolved_value=len(main_directions),
        unit="count",
        applicable_views=["top", "blade_3d"],
        feature_geometry=[
            _axis_feature("blade.main.count:axis", [1.0, 0.0]),
            *_top_context_features(surface_graph),
        ],
        dimension_definition=None,
        selection_scope={"source_geometry_kind": "blade_population"},
    )
    if len(main_directions) >= 2:
        append(
            parameter_id="blade.angular_pitch",
            group_id="blade_placement",
            label="Angular pitch",
            requested_value=_angle_degrees(main_directions[0], main_directions[1]),
            resolved_value=_angle_degrees(main_directions[0], main_directions[1]),
            unit="deg",
            applicable_views=["top", "blade_3d"],
            feature_geometry=[
                _axis_feature("blade.angular_pitch:reference", main_directions[0]),
                _axis_feature("blade.angular_pitch:measured", main_directions[1]),
            ],
            dimension_definition=_angular_dimension(main_directions[0], main_directions[1]),
            selection_scope={"source_geometry_kind": "blade_placement"},
        )
    splitter_directions = _blade_anchor_directions(blade_instances, surface_by_id, "splitter")
    if main_directions and splitter_directions:
        splitter_value: Any = _angle_degrees(main_directions[0], splitter_directions[0])
        splitter_definition: Mapping[str, Any] | None = _angular_dimension(
            main_directions[0], splitter_directions[0]
        )
    else:
        splitter_value = "not_applicable"
        splitter_definition = None
    append(
        parameter_id="blade.splitter.phase",
        group_id="blade_placement",
        label="Splitter phase",
        requested_value=splitter_value,
        resolved_value=splitter_value,
        unit="deg" if splitter_definition else "status",
        applicable_views=["top", "blade_3d"],
        feature_geometry=[_axis_feature("blade.splitter.phase:axis", main_directions[0] if main_directions else [1.0, 0.0])],
        dimension_definition=splitter_definition,
        selection_scope={"source_geometry_kind": "blade_placement"},
    )

    for station_id, station in span_stations.items():
        loop_id = station["section_loop_id"]
        loop = section_loops[loop_id]
        blade_id = station["blade_instance_id"]
        station_index = station["source_loop_index"]
        scope = {
            "blade_instance_id": blade_id,
            "span_station_id": station_id,
            "section_loop_id": loop_id,
            "source_station_index": station_index,
        }
        point = _station_reference_point(loop)
        pose_parameter_id = f"blade:{blade_id}:pose.station.{station_index}"
        append(
            parameter_id=pose_parameter_id,
            group_id="spanwise_pose",
            label=f"Spanwise station {station_index}",
            requested_value=station.get("h"),
            resolved_value=station.get("h"),
            unit="span fraction",
            applicable_views=["s_q"],
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
        )
        for segment_name, segment in loop["segment_references"].items():
            segment_id = segment["section_segment_id"]
            for index, record in enumerate(segment["control_points"]):
                coordinates = record["display_coordinates_s_q_mm"]
                for axis, axis_index in (("s", 0), ("q", 1)):
                    parameter_id = (
                        f"blade:{blade_id}:station:{station_id}:section:{segment_name}:control:{index}:{axis}"
                    )
                    append(
                        parameter_id=parameter_id,
                        group_id="section_loop",
                        label=f"{segment_name} control {index} {axis}",
                        requested_value=coordinates[axis_index],
                        resolved_value=abs(float(coordinates[axis_index])),
                        unit="mm",
                        applicable_views=["s_q"],
                        feature_geometry=[
                            {
                                "kind": "control_point",
                                "id": f"{parameter_id}:control_point",
                                "coordinate_system": "s_q_mm",
                                "coordinates": copy.deepcopy(coordinates),
                            }
                        ],
                        dimension_definition=_coordinate_dimension(coordinates, axis_index, "mm"),
                        selection_scope={
                            **scope,
                            "section_segment_id": segment_id,
                            "source_segment_name": segment_name,
                            "source_control_index": index,
                            "source_control_point_id": record["control_point_id"],
                        },
                    )
            if segment_name not in {"leading_edge", "trailing_edge"}:
                continue
            points = segment["display_points_s_q_mm"]
            points_xyz = segment["points_xyz"]
            sagitta_points = [copy.deepcopy(points[0]), copy.deepcopy(points[-1]), copy.deepcopy(points[len(points) // 2])]
            parameter_id = f"blade:{blade_id}:station:{station_id}:section:{segment_name}:sagitta"
            append(
                parameter_id=parameter_id,
                group_id="section_loop",
                label=f"{segment_name} sagitta",
                requested_value=_point_line_distance(sagitta_points[2], sagitta_points[0], sagitta_points[1]),
                resolved_value=_point_line_distance(sagitta_points[2], sagitta_points[0], sagitta_points[1]),
                unit="mm",
                applicable_views=["s_q", "blade_3d"],
                feature_geometry=[
                    {
                        "kind": "polyline",
                        "id": f"{parameter_id}:curve",
                        "coordinate_system": "model_xyz",
                        "points": copy.deepcopy(points_xyz),
                        "display_points_s_q_mm": copy.deepcopy(points),
                    },
                    *_sagitta_measurement_features(parameter_id, points_xyz, points),
                ],
                dimension_definition={
                    "kind": "arc_height",
                    "measurement_points": sagitta_points,
                    "unit": "mm",
                    "tolerance": 1.0e-6,
                },
                selection_scope={
                    **scope,
                    "section_segment_id": segment_id,
                    "source_segment_name": segment_name,
                },
            )

        for join_name, metrics in loop.get("join_metrics", {}).items():
            for metric_name, unit in (
                ("position_gap_mm", "mm"),
                ("tangent_angle_deg", "deg"),
                ("normal_angle_deg", "deg"),
                ("curvature_proxy_mismatch", "ratio"),
                ("status", "status"),
            ):
                if metric_name not in metrics:
                    continue
                parameter_id = f"blade:{blade_id}:station:{station_id}:join:{join_name}:{metric_name}"
                append(
                    parameter_id=parameter_id,
                    group_id="inspection_results",
                    label=f"{join_name} {metric_name}",
                    requested_value=metrics[metric_name],
                    resolved_value=metrics[metric_name],
                    unit=unit,
                    applicable_views=["s_q"],
                    feature_geometry=[{
                        "kind": "polyline",
                        "id": f"{parameter_id}:loop",
                        "coordinate_system": "s_q_mm",
                        "points": _section_loop_points(loop),
                    }],
                    dimension_definition=None,
                    selection_scope={
                        **scope,
                        "source_join_name": join_name,
                        "source_join_metric": metric_name,
                    },
                )

    _append_attachment_parameters(parameters, blade_instances, span_stations, section_loops, surface_by_id)
    _append_shroud_thickness_parameter(parameters, surface_by_id)


def _append_canonical_field_parameters(
    parameters: list[dict[str, Any]], canonical: Mapping[str, Any]
) -> None:
    def append(**kwargs: Any) -> None:
        parameters.append(_inspection_parameter(order=len(parameters), **kwargs))

    for field_name, group_id, label, value_axis, unit in (
        ("blade_skeleton_field", "spanwise_pose", "Blade skeleton", 2, "mm"),
        ("pose_field", "spanwise_pose", "Pose theta offset", 2, "deg"),
        ("thickness_field", "section_loop", "Thickness distribution", 2, "mm"),
    ):
        field = canonical.get(field_name)
        if not isinstance(field, Mapping):
            continue
        controls = field.get("control_points")
        if not isinstance(controls, list):
            continue
        display_points = [
            [float(point[0]), float(point[value_axis])]
            for row in controls if isinstance(row, list)
            for point in row if _coordinate_vector(point) and len(point) > value_axis
        ]
        if not display_points:
            continue
        feature = {
            "kind": "polyline",
            "id": "",
            "coordinate_system": "s_q_mm",
            "points": display_points,
        }
        for metadata_name in ("degree_u", "degree_v", "knots_u", "knots_v", "weights"):
            if metadata_name not in field:
                continue
            value = field[metadata_name]
            append(
                parameter_id=f"canonical.{field_name}.{metadata_name}",
                group_id=group_id,
                label=f"{label} {metadata_name}",
                requested_value=value,
                resolved_value=value,
                unit="degree" if metadata_name.startswith("degree") else "nurbs",
                applicable_views=["s_q"],
                feature_geometry=[{**feature, "id": f"canonical.{field_name}.{metadata_name}:net"}],
                dimension_definition=None,
                selection_scope={"source_canonical_path": [field_name, metadata_name]},
            )
        for row_index, row in enumerate(controls):
            if not isinstance(row, list):
                continue
            for column_index, point in enumerate(row):
                if not _coordinate_vector(point) or len(point) <= value_axis:
                    continue
                coordinates = [float(point[0]), float(point[value_axis])]
                append(
                    parameter_id=f"canonical.{field_name}.control.{row_index}.{column_index}.value",
                    group_id=group_id,
                    label=f"{label} control {row_index},{column_index}",
                    requested_value=point[value_axis],
                    resolved_value=point[value_axis],
                    unit=unit,
                    applicable_views=["s_q"],
                    feature_geometry=[{
                        "kind": "control_point",
                        "id": f"canonical.{field_name}.control.{row_index}.{column_index}:point",
                        "coordinate_system": "s_q_mm",
                        "coordinates": coordinates,
                    }],
                    dimension_definition=None,
                    selection_scope={
                        "source_canonical_path": [field_name, "control_points", row_index, column_index, value_axis]
                    },
                )


def _coordinate_dimension(point: Sequence[float], axis_index: int, unit: str) -> dict[str, Any]:
    origin = copy.deepcopy(list(point))
    origin[axis_index] = 0.0
    return {
        "kind": "control_coordinate",
        "measurement_points": [origin, copy.deepcopy(list(point))],
        "unit": unit,
        "tolerance": 1.0e-6,
    }


def _axis_feature(primitive_id: str, direction: Sequence[float]) -> dict[str, Any]:
    return {
        "kind": "reference_axis",
        "id": primitive_id,
        "coordinate_system": "model_xyz",
        "origin": [0.0, 0.0, 0.0],
        "direction": [float(direction[0]), float(direction[1]), 0.0],
    }


def _angular_dimension(reference_direction: Sequence[float], measured_direction: Sequence[float]) -> dict[str, Any]:
    return {
        "kind": "angular",
        "measurement_points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        "reference_direction": [float(reference_direction[0]), float(reference_direction[1]), 0.0],
        "measured_direction": [float(measured_direction[0]), float(measured_direction[1]), 0.0],
        "unit": "deg",
        "tolerance": 1.0e-6,
    }


def _top_context_features(surface_graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    blades = surface_graph.get("blade_to_blade_loop_family", {}).get("blades", [])
    for blade_index, blade in enumerate(blades):
        loops = blade.get("loops", []) if isinstance(blade, Mapping) else []
        if not loops:
            continue
        for segment_name, segment in loops[0].get("segments", {}).items():
            points = segment.get("points_xyz", []) if isinstance(segment, Mapping) else []
            if not _coordinate_array(points, minimum_count=2):
                continue
            features.append(
                {
                    "kind": "polyline",
                    "id": f"top_context:blade_{blade_index}:{segment_name}",
                    "coordinate_system": "model_xyz",
                    "rendering_role": "drawing_context",
                    "points": copy.deepcopy(points),
                }
            )
    return features


def _blade_anchor_directions(
    blade_instances: Mapping[str, Any], surface_by_id: Mapping[str, Mapping[str, Any]], blade_class: str
) -> list[list[float]]:
    directions: list[list[float]] = []
    for blade in blade_instances.values():
        if blade.get("blade_class") != blade_class:
            continue
        surface = next(
            (
                surface_by_id[surface_id]
                for surface_id in blade.get("surface_ids", [])
                if surface_by_id[surface_id].get("role") == "root_to_hub_attachment"
            ),
            None,
        )
        if surface is None:
            continue
        point = surface.get("uv_grid", [[None]])[-1][0]
        if not _coordinate_vector(point) or len(point) < 3:
            continue
        direction = [float(point[0]), float(point[1])]
        if _vector_norm(direction) > 1.0e-9:
            directions.append(direction)
    return directions


def _append_attachment_parameters(
    parameters: list[dict[str, Any]],
    blade_instances: Mapping[str, Any],
    span_stations: Mapping[str, Any],
    section_loops: Mapping[str, Any],
    surface_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    def append(**kwargs: Any) -> None:
        parameters.append(_inspection_parameter(order=len(parameters), **kwargs))

    for blade_id, blade in blade_instances.items():
        station_ids = blade.get("span_station_ids", [])
        if not station_ids:
            continue
        station_id = station_ids[0]
        loop_id = span_stations[station_id]["section_loop_id"]
        scope = {
            "blade_instance_id": blade_id,
            "span_station_id": station_id,
            "section_loop_id": loop_id,
            "source_station_index": span_stations[station_id]["source_loop_index"],
        }
        blade_index = blade["blade_index"]
        root_surface = next(
            (
                surface_by_id[surface_id]
                for surface_id in blade["surface_ids"]
                if surface_by_id[surface_id].get("role") == "root_to_hub_attachment"
            ),
            None,
        )
        if root_surface is not None:
            _append_attachment_measurements(append, f"blade:{blade_id}:attachment:root", root_surface, scope, "root")
        shroud_surface = next(
            (
                surface_by_id[surface_id]
                for surface_id in blade["surface_ids"]
                if surface_by_id[surface_id].get("role") == "closed_shroud_attachment"
            ),
            None,
        )
        if shroud_surface is not None:
            _append_attachment_measurements(
                append, f"blade:{blade_id}:attachment:shroud", shroud_surface, scope, "shroud"
            )


def _append_attachment_measurements(
    append: Any,
    prefix: str,
    surface: Mapping[str, Any],
    scope: Mapping[str, Any],
    attachment: str,
) -> None:
    domain_key = "v1_1_root_domain_samples" if attachment == "root" else "v1_1_shroud_domain_samples"
    source_key, target_key = (
        ("hub_outer_loop_s_q", "blade_inner_loop_s_q")
        if attachment == "root"
        else ("blade_tip_loop_s_q", "shroud_attachment_loop_s_q")
    )
    domain = surface.get(domain_key, {})
    quality = surface.get("v1_1_root_quality", {}) or surface.get("v1_1_tip_quality", {})
    scale = quality.get("root_streamwise_metric_scale_mm")
    source = domain.get(source_key, []) if isinstance(domain, Mapping) else []
    target = domain.get(target_key, []) if isinstance(domain, Mapping) else []
    if attachment == "root" and _finite_number(scale) and source and target:
        width_points = _metric_s_q_points([source[0], target[0]], float(scale))
        edges = surface.get("edge_samples", {})
        model_points = [edges.get("hub_outer_loop", [None])[0], edges.get("blade_inner_loop", [None])[0]]
        _append_linear_parameter(
            append,
            f"{prefix}:width",
            f"{attachment.title()} attachment width",
            width_points,
            {
                **scope,
                "source_attachment_surface_id": surface["id"],
                "source_attachment_measurement": "root_width",
            },
            "model_xyz",
            selected_points=model_points,
            display_points_s_q_mm=width_points,
            context_features=_attachment_context_features(f"{prefix}:width", surface, attachment),
        )
    elif attachment == "shroud":
        edges = surface.get("edge_samples", {})
        width_points = [
            edges.get("shroud_reference_loop", [None])[0],
            edges.get("shroud_attachment_loop", [None])[0],
        ]
        if all(_coordinate_vector(point) for point in width_points):
            _append_linear_parameter(
                append,
                f"{prefix}:width",
                "Shroud attachment width",
                width_points,
                {
                    **scope,
                    "source_attachment_surface_id": surface["id"],
                    "source_attachment_measurement": "shroud_width",
                },
                "model_xyz",
                context_features=_attachment_context_features(f"{prefix}:width", surface, attachment),
            )
    if attachment == "root":
        rows = surface.get("uv_grid", [])
        lift_points = [rows[0][0], rows[-1][0]] if rows and rows[0] and rows[-1] else []
    else:
        edges = surface.get("edge_samples", {})
        lift_points = [edges.get("blade_tip_loop", [None])[0], edges.get("shroud_reference_loop", [None])[0]]
    if len(lift_points) == 2 and all(_coordinate_vector(point) for point in lift_points):
        _append_linear_parameter(
            append,
            f"{prefix}:lift",
            f"{attachment.title()} attachment lift",
            lift_points,
            {
                **scope,
                "source_attachment_surface_id": surface["id"],
                "source_attachment_measurement": f"{attachment}_lift",
            },
            "model_xyz",
            context_features=_attachment_context_features(f"{prefix}:lift", surface, attachment),
        )


def _attachment_context_features(
    prefix: str,
    surface: Mapping[str, Any],
    attachment: str,
) -> list[dict[str, Any]]:
    edges = surface.get("edge_samples", {})
    boundary_keys = (
        (("hub_side", "hub_outer_loop"), ("blade_side", "blade_inner_loop"))
        if attachment == "root"
        else (("shroud_side", "shroud_reference_loop"), ("blade_side", "blade_tip_loop"))
    )
    features = []
    for boundary_role, edge_key in boundary_keys:
        points = edges.get(edge_key, []) if isinstance(edges, Mapping) else []
        if not _coordinate_array(points, minimum_count=2):
            continue
        features.append(
            {
                "kind": "polyline",
                "id": f"{prefix}:context:{boundary_role}",
                "coordinate_system": "model_xyz",
                "rendering_role": "drawing_context",
                "boundary_role": boundary_role,
                "points": copy.deepcopy(points),
            }
        )
    return features


def _append_linear_parameter(
    append: Any,
    parameter_id: str,
    label: str,
    points: Sequence[Sequence[float]],
    scope: Mapping[str, Any],
    coordinate_system: str,
    *,
    selected_points: Sequence[Sequence[float]] | None = None,
    display_points_s_q_mm: Sequence[Sequence[float]] | None = None,
    context_features: Sequence[Mapping[str, Any]] = (),
) -> None:
    measured = _distance(points[0], points[1])
    feature_points = selected_points or points
    selected_features = []
    for endpoint, point in zip(("start", "end"), feature_points):
        feature = {
            "kind": "point",
            "id": f"{parameter_id}:{endpoint}",
            "coordinate_system": coordinate_system,
            "coordinates": copy.deepcopy(list(point)),
        }
        if display_points_s_q_mm is not None:
            feature["display_coordinates_s_q_mm"] = copy.deepcopy(
                list(display_points_s_q_mm[0 if endpoint == "start" else 1])
            )
        selected_features.append(feature)
    append(
        parameter_id=parameter_id,
        group_id="attachments",
        label=label,
        requested_value=measured,
        resolved_value=measured,
        unit="mm",
        applicable_views=["meridional", "blade_3d"],
        feature_geometry=[*context_features, *selected_features],
        dimension_definition={
            "kind": "linear",
            "measurement_points": [copy.deepcopy(list(points[0])), copy.deepcopy(list(points[1]))],
            **(
                {"model_measurement_points": copy.deepcopy([list(point) for point in feature_points])}
                if selected_points is not None
                else {}
            ),
            "unit": "mm",
            "tolerance": 1.0e-6,
        },
        selection_scope=copy.deepcopy(dict(scope)),
    )


def _append_shroud_thickness_parameter(
    parameters: list[dict[str, Any]], surface_by_id: Mapping[str, Mapping[str, Any]]
) -> None:
    inner = next((surface for surface in surface_by_id.values() if surface.get("role") == "shroud_support"), None)
    outer = next(
        (
            surface
            for surface in surface_by_id.values()
            if surface.get("id") == "shroud_outer_material_surface"
        ),
        None,
    )
    if inner is None or outer is None:
        return
    inner_point = inner.get("uv_grid", [[None]])[0][0]
    outer_point = outer.get("uv_grid", [[None]])[0][0]
    if not _coordinate_vector(inner_point) or not _coordinate_vector(outer_point):
        return
    _append_linear_parameter(
        lambda **kwargs: parameters.append(_inspection_parameter(order=len(parameters), **kwargs)),
        "shroud.thickness",
        "Shroud thickness",
        [inner_point, outer_point],
        {
            "source_shroud_inner_surface_id": inner["id"],
            "source_shroud_outer_surface_id": outer["id"],
        },
        "model_xyz",
    )


def _station_reference_point(loop: Mapping[str, Any]) -> list[float]:
    pressure = loop["segment_references"]["pressure_side"]["display_points_s_q_mm"]
    return copy.deepcopy(pressure[len(pressure) // 2])


def _station_reference_point_xyz(loop: Mapping[str, Any]) -> list[float]:
    pressure = loop["segment_references"]["pressure_side"]["points_xyz"]
    return copy.deepcopy(pressure[len(pressure) // 2])


def _section_thickness_endpoints(loop: Mapping[str, Any]) -> list[list[float]]:
    pressure = loop["segment_references"]["pressure_side"]["display_points_s_q_mm"]
    suction = loop["segment_references"]["suction_side"]["display_points_s_q_mm"]
    sample_index = min(len(pressure), len(suction)) // 2
    return [copy.deepcopy(pressure[sample_index]), copy.deepcopy(suction[sample_index])]


def _section_thickness_endpoints_xyz(loop: Mapping[str, Any]) -> list[list[float]]:
    pressure = loop["segment_references"]["pressure_side"]["points_xyz"]
    suction = loop["segment_references"]["suction_side"]["points_xyz"]
    sample_index = min(len(pressure), len(suction)) // 2
    return [copy.deepcopy(pressure[sample_index]), copy.deepcopy(suction[sample_index])]


def _section_thickness_frame(loop: Mapping[str, Any]) -> dict[str, list[float]]:
    pressure = loop["segment_references"]["pressure_side"]["points_xyz"]
    suction = loop["segment_references"]["suction_side"]["points_xyz"]
    sample_index = min(len(pressure), len(suction)) // 2
    before = pressure[max(0, sample_index - 1)]
    after = pressure[min(len(pressure) - 1, sample_index + 1)]
    origin = pressure[sample_index]
    return {
        "origin": copy.deepcopy(origin),
        "s_axis": [float(right) - float(left) for left, right in zip(before, after)],
        "q_axis": [float(right) - float(left) for left, right in zip(origin, suction[sample_index])],
    }


def _distance_between_points(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((float(right_axis) - float(left_axis)) ** 2 for left_axis, right_axis in zip(left, right)))


def _section_loop_points(loop: Mapping[str, Any]) -> list[list[float]]:
    return [
        point
        for segment in loop["segment_references"].values()
        for point in segment["display_points_s_q_mm"]
    ]


def _section_loop_points_xyz(loop: Mapping[str, Any]) -> list[list[float]]:
    return [
        point
        for segment in loop["segment_references"].values()
        for point in segment["points_xyz"]
    ]


def _section_context_features(parameter_id: str, loop: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "kind": "polyline",
            "id": f"{parameter_id}:context:{segment_name}",
            "coordinate_system": "model_xyz",
            "rendering_role": "drawing_context",
            "source_segment_name": segment_name,
            "points": copy.deepcopy(segment["points_xyz"]),
            "display_points_s_q_mm": copy.deepcopy(segment["display_points_s_q_mm"]),
        }
        for segment_name, segment in loop["segment_references"].items()
    ]


def _sagitta_measurement_features(
    parameter_id: str,
    points_xyz: Sequence[Sequence[float]],
    display_points_s_q_mm: Sequence[Sequence[float]],
) -> list[dict[str, Any]]:
    indices = [0, len(points_xyz) - 1, len(points_xyz) // 2]
    return [
        {
            "kind": "point",
            "id": f"{parameter_id}:measurement:{label}",
            "coordinate_system": "model_xyz",
            "rendering_role": "selected_feature",
            "coordinates": copy.deepcopy(list(points_xyz[index])),
            "display_coordinates_s_q_mm": copy.deepcopy(list(display_points_s_q_mm[index])),
        }
        for label, index in zip(("start", "end", "arc"), indices)
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
    points_xyz = segment.get("points_xyz")
    controls = segment.get("control_points_s_q")
    display_points = segment.get("display_points_s_q_mm")
    display_controls = segment.get("display_control_points_s_q_mm")
    control_records = segment.get("control_points")
    if (
        not _nonempty_string(segment_id)
        or segment_id in segment_ids
        or not _point_array(points)
        or not _coordinate_array(points_xyz)
        or len(points_xyz) != len(points)
        or any(len(point) != 3 for point in points_xyz)
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
