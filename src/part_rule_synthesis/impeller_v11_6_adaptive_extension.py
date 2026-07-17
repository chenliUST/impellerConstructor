from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import numpy as np
from scipy.interpolate import make_interp_spline

CONTRACT_ID = "impeller_v1_1_6_adaptive_reconstruction_extension"
MINIMUM_STATION_COUNT = 5
MAXIMUM_STATION_COUNT = 9


def build_v116_adaptive_reconstruction_extension(
    measurements: Mapping[str, Any],
) -> dict[str, Any]:
    """Build an opt-in V1.1.2-compatible field bundle from measured sections."""

    try:
        families = _mapping(measurements.get("section_families"), "section_families")
        splitter = families.get("splitter")
        if isinstance(splitter, Mapping):
            return _rejection(
                "adaptive_splitter_population_fields_not_implemented",
                available_populations=sorted(str(name) for name in families),
            )
        main = _mapping(families.get("main"), "section_families.main")
        stations = list(_sequence(main.get("stations"), "section_families.main.stations"))
        if not MINIMUM_STATION_COUNT <= len(stations) <= MAXIMUM_STATION_COUNT:
            return _rejection(
                "adaptive_station_count_out_of_range",
                station_count=len(stations),
            )

        span_stations_h = [_finite(station.get("h"), f"stations[{index}].h") for index, station in enumerate(stations)]
        if any(
            upper <= lower
            for lower, upper in zip(span_stations_h, span_stations_h[1:])
        ):
            return _rejection("adaptive_span_stations_not_strictly_increasing")
        if abs(span_stations_h[0]) > 1.0e-9 or abs(span_stations_h[-1] - 1.0) > 1.0e-9:
            return _rejection("adaptive_span_endpoints_missing")

        field_specs = {
            "blade_skeleton_field": ("camber", "q_mm", "q_mm"),
            "thickness_field": (
                "normal_thickness",
                "thickness_mm",
                "thickness_mm",
            ),
            "pose_field": ("pose", "theta_deg", "theta_deg"),
        }
        fields: dict[str, dict[str, Any]] = {}
        measured_values: dict[str, np.ndarray] = {}
        for field_name, (role, value_key, value_name) in field_specs.items():
            u_samples, values = _station_values(stations, role, value_key)
            measured_values[field_name] = values
            fields[field_name] = _tensor_product_field(
                field_name,
                span_stations_h,
                u_samples,
                values,
                value_name,
            )

        thickness_values = measured_values["thickness_field"]
        if not np.all(np.isfinite(thickness_values)) or np.any(thickness_values <= 0.0):
            return _rejection("adaptive_thickness_not_strictly_positive")
        measured_minimum_thickness_mm = float(np.min(thickness_values))
        fitted_minimum_thickness_mm = _positive_surface_control_hull_minimum(
            fields["thickness_field"]
        )
        positivity_resolution = "cubic_positive_control_hull"
        if fitted_minimum_thickness_mm <= 0.0:
            u_samples, values = _station_values(
                stations, "normal_thickness", "thickness_mm"
            )
            fields["thickness_field"] = _tensor_product_field(
                "thickness_field",
                span_stations_h,
                u_samples,
                values,
                "thickness_mm",
                degree_u_cap=1,
                degree_v_cap=1,
            )
            fitted_minimum_thickness_mm = _positive_surface_control_hull_minimum(
                fields["thickness_field"]
            )
            positivity_resolution = "linear_positive_control_hull_fallback"
        if fitted_minimum_thickness_mm <= 0.0:
            return _rejection(
                "adaptive_thickness_field_not_strictly_positive",
                measured_minimum_thickness_mm=measured_minimum_thickness_mm,
                fitted_minimum_thickness_mm=fitted_minimum_thickness_mm,
            )
        minimum_thickness_mm = fitted_minimum_thickness_mm
        fields["thickness_field"]["minimum_thickness_mm"] = minimum_thickness_mm
        fields["thickness_field"]["measured_minimum_thickness_mm"] = (
            measured_minimum_thickness_mm
        )
        fields["thickness_field"]["minimum_thickness_policy"] = (
            "positive_nurbs_control_hull_lower_bound"
        )
        fields["thickness_field"]["positivity_resolution"] = positivity_resolution
        fields["thickness_field"]["positivity_proof"] = (
            "positive_scalar_control_coefficients_with_positive_weights"
        )
        attachment_fields = _attachment_fields(measurements)
        support_span_mapping = _source_support_span_mapping(
            stations,
            span_stations_h,
        )

        result = {
            "contract_id": CONTRACT_ID,
            "status": "PASS",
            "mode": "v116_step_reconstruction_opt_in",
            "geometry_patch_version": "1.1.2",
            "station_count": len(stations),
            "span_stations_h": span_stations_h,
            "minimum_thickness_mm": minimum_thickness_mm,
            "minimum_thickness_policy": "positive_nurbs_control_hull_lower_bound",
            **fields,
            **attachment_fields,
            "source_cap_curve_targets": _source_cap_targets(stations),
            "population_scope": {
                "field_authority": "main",
                "available_populations": sorted(str(name) for name in families),
                "splitter_requires_separate_future_field": False,
            },
        }
        if support_span_mapping is not None:
            result["source_support_span_mapping"] = support_span_mapping
        return result
    except (TypeError, ValueError) as exc:
        return _rejection("adaptive_measurement_schema_invalid", message=str(exc))


def _station_values(
    stations: Sequence[Mapping[str, Any]], role: str, value_key: str
) -> tuple[np.ndarray, np.ndarray]:
    common_u: np.ndarray | None = None
    rows: list[np.ndarray] = []
    for station_index, station in enumerate(stations):
        role_data = _mapping(
            station.get(role), f"stations[{station_index}].{role}"
        )
        samples = list(
            _sequence(
                role_data.get("samples"),
                f"stations[{station_index}].{role}.samples",
            )
        )
        if len(samples) < 2:
            raise ValueError(f"stations[{station_index}].{role}.samples needs two points")
        source_s = np.asarray(
            [_finite(sample.get("s"), "sample.s") for sample in samples],
            dtype=float,
        )
        source_values = np.asarray(
            [_finite(sample.get(value_key), f"sample.{value_key}") for sample in samples],
            dtype=float,
        )
        order = np.argsort(source_s)
        source_s = source_s[order]
        source_values = source_values[order]
        if np.any(np.diff(source_s) <= 0.0):
            raise ValueError(f"stations[{station_index}].{role}.samples s must be unique")
        span = source_s[-1] - source_s[0]
        if span <= 1.0e-12:
            raise ValueError(f"stations[{station_index}].{role}.samples has zero s span")
        normalized_u = (source_s - source_s[0]) / span
        if common_u is None:
            common_u = normalized_u
        rows.append(np.interp(common_u, normalized_u, source_values))
    assert common_u is not None
    return common_u, np.asarray(rows, dtype=float)


def _tensor_product_field(
    name: str,
    span_stations_h: Sequence[float],
    u_samples: np.ndarray,
    values_hu: np.ndarray,
    value_name: str,
    *,
    degree_u_cap: int = 3,
    degree_v_cap: int = 3,
) -> dict[str, Any]:
    h_samples = np.asarray(span_stations_h, dtype=float)
    degree_u = min(int(degree_u_cap), len(u_samples) - 1)
    degree_v = min(int(degree_v_cap), len(h_samples) - 1)

    along_u = make_interp_spline(u_samples, values_hu, axis=1, k=degree_u)
    # scipy places the interpolated axis first in ``c``.  Transpose explicitly;
    # shape-based inference is ambiguous for square 5x5 and 7x7 station nets.
    value_coefficients_hu = np.asarray(along_u.c, dtype=float).T
    along_h = make_interp_spline(
        h_samples,
        value_coefficients_hu,
        axis=0,
        k=degree_v,
    )
    value_coefficients_hu = np.asarray(along_h.c, dtype=float)

    u_identity = make_interp_spline(
        u_samples, u_samples, k=degree_u
    ).c.astype(float)
    h_identity = make_interp_spline(
        h_samples, h_samples, k=degree_v
    ).c.astype(float)
    control_points = [
        [
            [float(u_identity[i]), float(h_identity[j]), float(value_coefficients_hu[j, i])]
            for j in range(len(h_identity))
        ]
        for i in range(len(u_identity))
    ]
    return {
        "kind": "nurbs_surface",
        "id": f"v116_adaptive_{name}",
        "coordinate_system": "normalized_streamwise_span_field",
        "value_component": value_name,
        "degree_u": degree_u,
        "degree_v": degree_v,
        "knots_u": [float(value) for value in along_u.t],
        "knots_v": [float(value) for value in along_h.t],
        "control_points": control_points,
        "weights": [
            [1.0 for _ in range(len(h_identity))]
            for _ in range(len(u_identity))
        ],
        "source": "direct_measured_section_interpolation",
    }


def _positive_surface_control_hull_minimum(field: Mapping[str, Any]) -> float:
    """Return a certified scalar lower bound for a positive-weight NURBS field."""

    controls = np.asarray(field.get("control_points"), dtype=float)
    weights = np.asarray(field.get("weights"), dtype=float)
    if (
        controls.ndim != 3
        or controls.shape[2] < 3
        or weights.shape != controls.shape[:2]
        or not np.all(np.isfinite(controls[:, :, 2]))
        or not np.all(np.isfinite(weights))
        or np.any(weights <= 0.0)
    ):
        return float("-inf")
    return float(np.min(controls[:, :, 2]))


def _source_support_span_mapping(
    stations: Sequence[Mapping[str, Any]],
    span_stations_h: Sequence[float],
) -> dict[str, Any] | None:
    present = ["support_span_h" in station for station in stations]
    if not any(present):
        return None
    if not all(present):
        raise ValueError("support_span_h must be present at every adaptive station")
    support_h = np.asarray(
        [
            _finite(station["support_span_h"], f"stations[{index}].support_span_h")
            for index, station in enumerate(stations)
        ],
        dtype=float,
    )
    active_h = np.asarray(span_stations_h, dtype=float)
    if support_h[0] < 0.0 or support_h[-1] > 1.0 or np.any(np.diff(support_h) <= 0.0):
        raise ValueError("support_span_h must increase strictly inside [0, 1]")

    degree = min(3, len(active_h) - 1)
    spline = make_interp_spline(active_h, support_h, k=degree)
    dense = np.asarray(spline(np.linspace(0.0, 1.0, 257)), dtype=float)
    resolution = "cubic_monotone_verified"
    if (
        np.min(dense) < support_h[0] - 1.0e-10
        or np.max(dense) > support_h[-1] + 1.0e-10
        or np.any(np.diff(dense) <= 0.0)
    ):
        degree = 1
        spline = make_interp_spline(active_h, support_h, k=degree)
        resolution = "linear_monotone_fallback"
    identity = make_interp_spline(active_h, active_h, k=degree)
    return {
        "kind": "nurbs_curve",
        "id": "v116_measured_active_to_support_span_mapping",
        "coordinate_system": "normalized_active_span_to_meridional_support_span",
        "components": ["active_h", "support_h"],
        "degree": int(spline.k),
        "knots": [float(value) for value in spline.t],
        "control_points": [
            [float(identity.c[index]), float(value)]
            for index, value in enumerate(np.asarray(spline.c, dtype=float))
        ],
        "weights": [1.0 for _ in spline.c],
        "source": "exact_section_support_span_positions",
        # The raw support positions describe where the exact section solver
        # could isolate blade-body loops.  They are not a global construction
        # offset: the local hub-to-tip separation and the measured attachment
        # lift both vary with streamwise position.
        "construction_usage": "measurement_station_provenance_only",
        "monotonicity_resolution": resolution,
        "support_span_interval_h": [float(support_h[0]), float(support_h[-1])],
    }


def _source_cap_targets(stations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    targets: dict[str, list[dict[str, Any]]] = {
        "leading_edge": [],
        "trailing_edge": [],
    }
    rejected_targets: list[dict[str, Any]] = []
    for station in stations:
        decomposition = station.get("decomposition")
        if not isinstance(decomposition, Mapping):
            continue
        segments = decomposition.get("segments")
        if not isinstance(segments, Mapping):
            continue
        for edge_name in targets:
            segment = segments.get(edge_name)
            if not isinstance(segment, Mapping):
                continue
            nurbs_target = segment.get("nurbs_target")
            if not isinstance(nurbs_target, Mapping):
                continue
            if nurbs_target.get("constructor_direct_curve_mode") is not True:
                rejected_targets.append(
                    {
                        "edge": edge_name,
                        "h": float(station["h"]),
                        "reason": (
                            "section_closure_has_no_authenticated_direct_cap_curve"
                        ),
                    }
                )
                continue
            if int(nurbs_target.get("degree", 0)) < 3:
                rejected_targets.append(
                    {
                        "edge": edge_name,
                        "h": float(station["h"]),
                        "reason": "authenticated_cap_curve_degree_below_three",
                    }
                )
                continue
            targets[edge_name].append(
                {
                    "h": float(station["h"]),
                    "nurbs_target": _geometry_only_curve_target(nurbs_target),
                }
            )
    return {
        "mode": "authenticated_direct_cap_curves_only",
        "leading_edge": targets["leading_edge"],
        "trailing_edge": targets["trailing_edge"],
        "rejected_target_count": len(rejected_targets),
        "rejected_targets": rejected_targets,
    }


def _geometry_only_curve_target(target: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "degree",
        "knots",
        "weights",
        "control_points_local_mm",
    )
    return {
        key: deepcopy(target[key])
        for key in allowed
        if key in target
    }


def _attachment_fields(measurements: Mapping[str, Any]) -> dict[str, Any]:
    attachments = measurements.get("attachments")
    if not isinstance(attachments, Mapping):
        return {}
    populations = measurements.get("populations")
    main = populations.get("main") if isinstance(populations, Mapping) else None
    interval = (
        main.get("streamwise_interval_s", [0.0, 1.0])
        if isinstance(main, Mapping)
        else [0.0, 1.0]
    )
    s0, s1 = float(interval[0]), float(interval[1])
    span = s1 - s0
    if span <= 1.0e-12:
        raise ValueError("main streamwise interval has zero span")
    result: dict[str, Any] = {}
    for attachment_name, output_name in (
        ("root", "root_attachment_field"),
        ("shroud", "shroud_attachment_field"),
    ):
        record = attachments.get(attachment_name)
        if not isinstance(record, Mapping) or "streamwise_samples_s" not in record:
            continue
        source_s = np.asarray(record["streamwise_samples_s"], dtype=float)
        widths = np.asarray(record["width_samples_mm"], dtype=float)
        lifts = np.asarray(record["lift_samples_mm"], dtype=float)
        if not (len(source_s) == len(widths) == len(lifts)) or len(source_s) < 3:
            raise ValueError(f"{attachment_name} attachment samples are inconsistent")
        if (
            not np.all(np.isfinite(source_s))
            or not np.all(np.isfinite(widths))
            or not np.all(np.isfinite(lifts))
            or np.any(widths <= 0.0)
            or np.any(lifts <= 0.0)
        ):
            raise ValueError(f"{attachment_name} attachment samples must be positive")
        normalized_u = np.clip((source_s - s0) / span, 0.0, 1.0)
        order = np.argsort(normalized_u)
        normalized_u = normalized_u[order]
        widths = widths[order]
        lifts = lifts[order]
        unique_u, inverse = np.unique(normalized_u, return_inverse=True)
        grouped = np.asarray(
            [
                [
                    float(np.mean(widths[inverse == index])),
                    float(np.mean(lifts[inverse == index])),
                ]
                for index in range(len(unique_u))
            ],
            dtype=float,
        )
        if unique_u[0] > 0.0:
            unique_u = np.insert(unique_u, 0, 0.0)
            grouped = np.vstack([grouped[0], grouped])
        if unique_u[-1] < 1.0:
            unique_u = np.append(unique_u, 1.0)
            grouped = np.vstack([grouped, grouped[-1]])
        degree = min(3, len(unique_u) - 1)
        spline = make_interp_spline(unique_u, grouped, axis=0, k=degree)
        positivity_resolution = "cubic_positive_control_hull"
        coefficients = np.asarray(spline.c, dtype=float)
        if np.any(coefficients <= 0.0):
            degree = 1
            spline = make_interp_spline(unique_u, grouped, axis=0, k=degree)
            positivity_resolution = "linear_positive_control_hull_fallback"
            coefficients = np.asarray(spline.c, dtype=float)
        if not np.all(np.isfinite(coefficients)) or np.any(coefficients <= 0.0):
            raise ValueError(
                f"{attachment_name} attachment field has no positive control-hull proof"
            )
        identity = make_interp_spline(unique_u, unique_u, k=degree)
        result[output_name] = {
            "kind": "nurbs_curve",
            "id": f"v116_adaptive_{attachment_name}_attachment_field",
            "coordinate_system": "normalized_streamwise_width_lift_mm",
            "components": ["u", "width_mm", "lift_mm"],
            "degree": int(spline.k),
            "knots": [float(value) for value in spline.t],
            "control_points": [
                [float(identity.c[index]), float(values[0]), float(values[1])]
                for index, values in enumerate(coefficients)
            ],
            "weights": [1.0 for _ in spline.c],
            "source": "paired_boundary_support_normal_decomposition",
            "minimum_width_mm": float(np.min(coefficients[:, 0])),
            "maximum_width_mm": float(np.max(coefficients[:, 0])),
            "minimum_lift_mm": float(np.min(coefficients[:, 1])),
            "maximum_lift_mm": float(np.max(coefficients[:, 1])),
            "positivity_resolution": positivity_resolution,
            "positivity_proof": (
                "positive_scalar_control_coefficients_with_positive_weights"
            ),
        }
    return result


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must be a mapping")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{path} must be a sequence")
    return value


def _finite(value: Any, path: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{path} must be finite")
    return number


def _rejection(reason: str, **details: Any) -> dict[str, Any]:
    return {
        "contract_id": CONTRACT_ID,
        "status": "REJECTED",
        "failure_reason": reason,
        **details,
    }
