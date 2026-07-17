from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from part_rule_synthesis.impeller_v11_constants import COORDINATE_SYSTEM, DOMAIN_ID, FACE_SEGMENTS, SPAN_STATIONS_H
from part_rule_synthesis.impeller_v11_blade_to_blade_loop import _join_metrics


_V11_DOMAIN_MAP_KIND = "v1_1_blade_to_blade_domain_mapper"
_V11_DOMAIN_MAP_PUBLIC_FUNCTION = "map_v11_domain_sample"
_V11_DOMAIN_MAP_SAMPLE_KEYS = ["s", "q", "h", "phase_offset_pitch"]
_V11_DOMAIN_MAP_Q_UNITS = "mm_arc_length"
_V11_DOMAIN_MAP_PHASE_OFFSET_PITCH_UNITS = "blade_pitch"
_V11_RESOLVED_DEFAULT_KEYS = (
    "main_streamwise_interval_s",
    "splitter_streamwise_interval_s",
    "splitter_phase_offset_pitch",
)


def validate_v11_loop_family(loop_family: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    failures.extend(_validate_loop_family_invariants(loop_family))
    control_minimums = loop_family.get("segment_control_count_minimums", {})
    for blade in loop_family.get("blades", []):
        for loop in blade.get("loops", []):
            failures.extend(_validate_loop(loop, control_minimums))
    return failures


def _validate_loop_family_invariants(loop_family: Mapping[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if loop_family.get("coordinate_system") != COORDINATE_SYSTEM:
        failures.append(_failure("v1_1_loop_orientation_failed"))
    if not _span_station_contract_is_valid(loop_family):
        failures.append(_failure("v1_1_loop_station_knot_mismatch"))
    failures.extend(_validate_domain_map(loop_family.get("domain_map")))
    expected_defaults, default_failures = _resolved_blade_graph_defaults(loop_family)
    failures.extend(default_failures)
    failures.extend(_validate_blade_graph_invariants(loop_family.get("blades", []), expected_defaults))
    metrics = loop_family.get("metrics")
    if isinstance(metrics, Mapping) and metrics.get("splitter_positioning_status") == "FAIL":
        failures.append(
            _failure(
                "v1_1_main_splitter_passage_collision",
                minimum_fraction=metrics.get("splitter_passage_fraction_min"),
                maximum_fraction=metrics.get("splitter_passage_fraction_max"),
            )
        )
    support_metrics = loop_family.get("support_profile_contract_metrics")
    if isinstance(support_metrics, Mapping) and support_metrics.get("status") == "FAIL":
        failures.append(
            _failure(
                "v1_1_4_support_profile_contract_failed",
                minimum_angle_deg=support_metrics.get("minimum_angle_deg"),
                maximum_angle_deg=support_metrics.get("maximum_angle_deg"),
                minimum_active_blade_height_mm=support_metrics.get("minimum_active_blade_height_mm"),
            )
        )
    return failures


def _span_station_contract_is_valid(loop_family: Mapping[str, Any]) -> bool:
    stations = loop_family.get("span_stations_h")
    if stations == SPAN_STATIONS_H:
        return True
    canonical = loop_family.get("canonical_nurbs_parameterization")
    if not isinstance(canonical, Mapping):
        return False
    extension = canonical.get("adaptive_reconstruction_extension")
    if not isinstance(extension, Mapping):
        return False
    expected = canonical.get("section_loop_family", {}).get("span_stations_h")
    if (
        extension.get("contract_id")
        != "impeller_v1_1_6_adaptive_reconstruction_extension"
        or extension.get("status") != "PASS"
        or extension.get("mode") != "v116_step_reconstruction_opt_in"
        or canonical.get("canonical_payload_version") != "1.1.2"
        or not isinstance(expected, list)
        or not 5 <= len(expected) <= 9
        or extension.get("station_count") != len(expected)
        or stations != expected
    ):
        return False
    try:
        values = [float(value) for value in expected]
    except (TypeError, ValueError):
        return False
    return (
        abs(values[0]) <= 1.0e-9
        and abs(values[-1] - 1.0) <= 1.0e-9
        and all(upper > lower for lower, upper in zip(values, values[1:]))
    )


def _validate_domain_map(domain_map: Any) -> list[dict[str, Any]]:
    if isinstance(domain_map, Callable):
        return [_failure("v1_1_loop_orientation_failed", component="domain_map", issue="callable")]
    if not isinstance(domain_map, Mapping):
        return [_failure("v1_1_loop_orientation_failed", component="domain_map", issue="not_dict")]
    expected_metadata = {
        "kind": _V11_DOMAIN_MAP_KIND,
        "public_function": _V11_DOMAIN_MAP_PUBLIC_FUNCTION,
        "coordinate_system": COORDINATE_SYSTEM,
        "domain_id": DOMAIN_ID,
        "q_units": _V11_DOMAIN_MAP_Q_UNITS,
        "phase_offset_pitch_units": _V11_DOMAIN_MAP_PHASE_OFFSET_PITCH_UNITS,
    }
    for key, expected in expected_metadata.items():
        if domain_map.get(key) != expected:
            return [_failure("v1_1_loop_orientation_failed", component="domain_map", field=key)]
    if domain_map.get("sample_keys") != _V11_DOMAIN_MAP_SAMPLE_KEYS:
        return [_failure("v1_1_loop_orientation_failed", component="domain_map", field="sample_keys")]
    return []


def _resolved_blade_graph_defaults(
    loop_family: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    defaults = loop_family.get("resolved_defaults")
    if not isinstance(defaults, Mapping):
        defaults = loop_family.get("resolved_blade_to_blade_loop_family_defaults")
    if not isinstance(defaults, Mapping):
        return {}, [
            _failure(
                "v1_1_loop_station_knot_mismatch",
                component="resolved_defaults",
                issue="missing",
            )
        ]
    missing = [key for key in _V11_RESOLVED_DEFAULT_KEYS if key not in defaults]
    if missing:
        return {}, [
            _failure(
                "v1_1_loop_station_knot_mismatch",
                component="resolved_defaults",
                issue="missing_keys",
                missing_keys=missing,
            )
        ]
    return dict(defaults), []


def _validate_blade_graph_invariants(blades: Any, expected_defaults: Mapping[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    expected_main_interval = expected_defaults.get("main_streamwise_interval_s")
    expected_splitter_interval = expected_defaults.get("splitter_streamwise_interval_s")
    expected_splitter_phase = expected_defaults.get("splitter_phase_offset_pitch")
    for blade in blades:
        if not isinstance(blade, Mapping):
            continue
        blade_class = str(blade.get("blade_class", ""))
        streamwise_interval_s = blade.get("streamwise_interval_s")
        if blade_class == "main":
            if streamwise_interval_s != expected_main_interval:
                failures.append(
                    _failure(
                        "v1_1_loop_station_knot_mismatch",
                        blade_class="main",
                        streamwise_interval_s=streamwise_interval_s,
                        expected_streamwise_interval_s=expected_main_interval,
                    )
                )
        elif blade_class == "splitter":
            if streamwise_interval_s != expected_splitter_interval:
                failures.append(
                    _failure(
                        "v1_1_loop_station_knot_mismatch",
                        blade_class="splitter",
                        streamwise_interval_s=streamwise_interval_s,
                        expected_streamwise_interval_s=expected_splitter_interval,
                    )
                )
            if blade.get("phase_offset_pitch") != expected_splitter_phase:
                failures.append(
                    _failure(
                        "v1_1_main_splitter_phase_failed",
                        blade_class="splitter",
                        phase_offset_pitch=blade.get("phase_offset_pitch"),
                        expected_phase_offset_pitch=expected_splitter_phase,
                    )
                )
    return failures


def _validate_loop(loop: Mapping[str, Any], control_minimums: Mapping[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    segments = loop.get("segments", {})
    for segment in FACE_SEGMENTS:
        data = segments.get(segment)
        controls = data.get("control_points_s_q", []) if isinstance(data, Mapping) else []
        fallback_minimum = 11 if segment in {"pressure_side", "suction_side"} else 9
        minimum = int(control_minimums.get(segment, fallback_minimum))
        if len(controls) < minimum:
            failures.append(_failure("v1_1_loop_control_count_insufficient", segment=segment))
    if all(isinstance(segments.get(segment), Mapping) for segment in FACE_SEGMENTS):
        measured = _join_metrics(
            segments,
            streamwise_metric_scale_mm=float(loop.get("streamwise_metric_scale_mm", 1.0)),
        )
        for join_name, metrics in measured.items():
            if metrics["status"] != "PASS":
                failures.append(_failure("v1_1_loop_join_c2_failed", join=join_name, metrics=dict(metrics)))
    return failures


def _failure(reason: str, **metadata: Any) -> dict[str, Any]:
    return {"status": "FAIL", "blocking": True, "stage": "v1_1_loop_validation", "reason": reason, **metadata}
