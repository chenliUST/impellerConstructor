from __future__ import annotations

import copy
import math
import os
import time
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.interpolate import BSpline, PchipInterpolator

from part_rule_synthesis.impeller_v10_topology_graph import build_v10_topology_graph
from part_rule_synthesis.impeller_v11_3_parameter_inspection import (
    build_parameter_inspection_contract,
)


IMPLEMENTATION_REVISION = "axis_first_attachment_patch_complex_r16_24"
_ExactPatchTemplate = tuple[
    int,
    int,
    Mapping[str, Any],
    Any,
    Mapping[str, Any],
    Sequence[Mapping[str, Any]],
]

_GRAPH_ROLE_BY_CURVE = {
    "side_a": "blade_pressure",
    "side_b": "blade_suction",
    "leading_edge": "blade_leading_edge",
    "trailing_edge": "blade_trailing_edge",
}
_FACE_LOCAL_TRIM_SEAM_KINDS = {
    "degenerate_trim_seam",
    "periodic_parameter_seam",
}


class DirectSectionSurfaceError(ValueError):
    def __init__(self, reason: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.details = dict(details or {})


def replace_blade_surfaces_with_direct_section_curves(
    surface_graph: Mapping[str, Any],
    mapping: Mapping[str, Any],
    *,
    span_sample_count: int = 49,
    curve_sample_count: int = 97,
) -> tuple[dict[str, Any], dict[str, Any]]:
    total_started = time.perf_counter()
    graph = _copy_surface_graph_for_direct_replacement(surface_graph)
    _emit_r16_timing("surface_graph_copy_on_write", total_started)
    network = _network(mapping)
    periodic = _periodic_populations(mapping)
    graph_surfaces = _surface_index(graph)
    population_manifests = []
    generated_loops = []
    replaced_surface_ids: set[str] = set()
    strict_attachment_topology = False

    for population_name, family in sorted(network["populations"].items()):
        population_started = time.perf_counter()
        stations = sorted(family["stations"], key=lambda station: float(station["active_h"]))
        closure_mode = _closure_mode(stations)
        base_grids, interpolation = _build_population_grids(
            stations,
            span_sample_count=span_sample_count,
            curve_sample_count=curve_sample_count,
            native_source_stream_sampling=bool(
                _active_span_authority(
                    family.get("active_span_authority")
                ).get("tip_surface_patches")
            ),
        )
        material_grids = (
            {
                role: grid
                for role, grid in base_grids.items()
                if role in {"side_a", "side_b"}
            }
            if closure_mode == "sharp_shared_seam"
            else base_grids
        )
        quality = _surface_quality(material_grids)
        quality["quality_scope"] = (
            "material_side_surfaces_only_sharp_edge_seams_are_topological"
            if closure_mode == "sharp_shared_seam"
            else "all_material_transition_surfaces"
        )
        exact_trim_roles = set(interpolation.get("exact_source_trim_roles", ()))
        exact_trim_authority = (
            closure_mode == "sharp_shared_seam"
            and exact_trim_roles == {"side_a", "side_b"}
        )
        carrier_observation_residual = (
            float(interpolation["station_surface_incidence_residual_max_mm"])
            if exact_trim_authority
            else _station_residual_max_mm(
                stations, base_grids, interpolation["span_samples_h"]
            )
        )
        quality["carrier_section_observation_residual_max_mm"] = (
            carrier_observation_residual
        )
        quality["carrier_section_observation_is_geometry_gate"] = True
        quality["geometry_authority"] = (
            "authenticated_step_trimmed_rational_bspline_surfaces"
            if exact_trim_authority
            else "direct_section_curve_network"
        )
        quality["authoritative_station_residual_max_mm"] = (
            carrier_observation_residual
        )
        quality["shared_boundary_gap_max_mm"] = _shared_boundary_gap_max_mm(
            base_grids
        )
        quality["shared_boundary_orientation_mismatch_count"] = (
            _shared_boundary_orientation_mismatch_count(base_grids)
        )
        tolerance = max(
            [float(station.get("source_tolerance_mm", 0.0)) for station in stations]
            or [0.0]
        )
        quality["source_tolerance_mm"] = tolerance
        quality["status"] = (
            "PASS"
            if quality["status"] == "PASS"
            and quality["authoritative_station_residual_max_mm"]
            <= max(2.0 * tolerance, 0.10)
            and quality["shared_boundary_gap_max_mm"] <= 0.05
            and quality["shared_boundary_orientation_mismatch_count"] == 0
            else "FAIL"
        )
        if quality["status"] != "PASS":
            raise DirectSectionSurfaceError(
                "v116_direct_curve_surface_quality_failed",
                f"direct section surface quality gate failed for {population_name}",
                quality,
            )
        population = periodic.get(population_name)
        if population is None:
            raise DirectSectionSurfaceError(
                "v116_direct_curve_population_missing",
                f"direct curve family {population_name!r} has no measured periodic population",
            )
        instance_manifests = []
        active_span_authority = _active_span_authority(
            family.get("active_span_authority")
        )
        strict_attachment_topology = strict_attachment_topology or bool(
            isinstance(
                active_span_authority.get("source_side_boundary_correspondence"),
                Mapping,
            )
            and active_span_authority["source_side_boundary_correspondence"].get(
                "status"
            )
            == "PASS"
        )
        exact_patch_templates = _population_exact_patch_templates(
            stations,
            active_span_authority,
        )
        _emit_r16_timing(
            f"{population_name}.exact_patch_templates",
            population_started,
            patch_count=sum(len(value) for value in exact_patch_templates.values()),
        )
        for raw_instance in population["instances"]:
            instance_started = time.perf_counter()
            instance = dict(raw_instance)
            index = int(instance["lattice_index"])
            transform = _rigid_matrix(instance["transform_from_representative"])
            replaced_ids = []
            transformed_grids = {}
            for curve_role, grid in base_grids.items():
                graph_role = _GRAPH_ROLE_BY_CURVE[curve_role]
                try:
                    surface = graph_surfaces[(population_name, index, graph_role)]
                except KeyError as exc:
                    raise DirectSectionSurfaceError(
                        "v116_direct_curve_surface_missing",
                        f"generated graph lacks {population_name}[{index}] {graph_role}",
                    ) from exc
                transformed = _transform_grid(grid, transform)
                transformed_grids[curve_role] = transformed
                side_templates = exact_patch_templates.get(curve_role)
                if curve_role in {"side_a", "side_b"} and side_templates:
                    replaced_ids.extend(
                        _replace_exact_trimmed_patch_surfaces(
                            graph["surfaces"],
                            surface,
                            (),
                            transform,
                            construction=(
                                "authenticated_source_blade_pressure_patch"
                                if curve_role == "side_a"
                                else "authenticated_source_blade_suction_patch"
                            ),
                            quality_key="v1_1_side_quality",
                            sampled_patches=side_templates,
                        )
                    )
                    continue
                if closure_mode == "sharp_shared_seam" and curve_role in {
                    "leading_edge",
                    "trailing_edge",
                }:
                    exact_edge_patches = active_span_authority.get(
                        f"{curve_role}_surface_patches"
                    )
                    if isinstance(exact_edge_patches, list) and exact_edge_patches:
                        replaced_ids.extend(
                            _replace_exact_trimmed_patch_surfaces(
                                graph["surfaces"],
                                surface,
                                exact_edge_patches,
                                transform,
                                construction=(
                                    f"authenticated_source_{curve_role}_patch"
                                ),
                                quality_key="v1_1_edge_quality",
                                sampled_patches=exact_patch_templates.get(
                                    curve_role
                                ),
                            )
                        )
                        continue
                    surface["material"] = False
                    surface["export_default"] = "excluded"
                    surface.setdefault("display", {})["visible_by_default"] = False
                    surface["source"] = {
                        "authority": "authenticated_step_shared_seam",
                        "implementation_revision": IMPLEMENTATION_REVISION,
                        "curve_role": curve_role,
                    }
                    surface["fidelity"] = "topological_shared_seam_no_finite_face"
                    replaced_ids.append(str(surface["id"]))
                    continue
                surface["uv_grid"] = transformed
                surface["edge_samples"] = {
                    "root": copy.deepcopy(transformed[0]),
                    "tip": copy.deepcopy(transformed[-1]),
                    "start": [copy.deepcopy(row[0]) for row in transformed],
                    "end": [copy.deepcopy(row[-1]) for row in transformed],
                }
                endpoint_bridge = bool(
                    closure_mode == "endpoint_witness_bridge_review_only"
                    and curve_role in {"leading_edge", "trailing_edge"}
                )
                trimmed_source_authority = curve_role in exact_trim_roles
                surface["source"] = {
                    "authority": (
                        "review_only_endpoint_witness_bridge"
                        if endpoint_bridge
                        else (
                            "authenticated_step_trimmed_rational_bspline_surface"
                            if trimmed_source_authority
                            else "authenticated_step_exact_section_curve_network"
                        )
                    ),
                    "implementation_revision": IMPLEMENTATION_REVISION,
                    "population": population_name,
                    "curve_role": curve_role,
                    "aerodynamic_role_status": "COMPATIBILITY_ROLE_UNRESOLVED_SIDE_A_SIDE_B",
                    "authoritative_station_count": len(stations),
                }
                surface["fidelity"] = (
                    "review_only_endpoint_bridge_without_source_curvature_authority"
                    if endpoint_bridge
                    else (
                        "sampled_review_grade_authenticated_trimmed_nurbs_surface"
                        if trimmed_source_authority
                        else "sampled_review_grade_direct_section_curve_loft"
                    )
                )
                replaced_ids.append(str(surface["id"]))
            attachment_ids = _replace_attachment_surfaces(
                graph["surfaces"],
                graph_surfaces,
                population_name,
                index,
                base_grids,
                transformed_grids,
                stations,
                family.get("active_span_authority"),
                transform,
                exact_patch_templates=exact_patch_templates,
            )
            replaced_ids.extend(attachment_ids)
            replaced_surface_ids.update(replaced_ids)
            instance_manifests.append(
                {
                    "lattice_index": index,
                    "transform_from_representative": transform.tolist(),
                    "surface_ids": sorted(replaced_ids),
                }
            )
            _emit_r16_timing(
                f"{population_name}.instance_{index:04d}",
                instance_started,
                surface_count=len(replaced_ids),
            )

        for station in stations:
            generated_loops.append(
                _generated_station_loop(
                    population_name,
                    station,
                    base_grids,
                    interpolation["span_samples_h"],
                    exact_source_trim_roles=exact_trim_roles,
                )
            )
        population_manifests.append(
            {
                "population": population_name,
                "authoritative_station_count": len(stations),
                "span_sample_count": len(interpolation["span_samples_h"]),
                "curve_sample_count": curve_sample_count,
                "closure_mode": closure_mode,
                "span_interpolation": "shape_preserving_pchip_through_exact_stations",
                "surface_correspondence": copy.deepcopy(
                    interpolation["surface_correspondence"]
                ),
                "instances": instance_manifests,
                "surface_quality": quality,
            }
        )
        _emit_r16_timing(
            f"{population_name}.population_complete",
            population_started,
            instance_count=len(instance_manifests),
        )

    attachment_started = time.perf_counter()
    attachment_topology = _attachment_topology_contract(
        graph["surfaces"],
        tolerance_mm=0.05,
        require_source_identity=strict_attachment_topology,
    )
    if attachment_topology["status"] == "FAIL":
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_quality_failed",
            "authenticated STEP attachment boundaries are not a closed shared-edge complex",
            attachment_topology,
        )
    _emit_r16_timing(
        "attachment_topology_contract",
        attachment_started,
        source_boundary_count=attachment_topology.get(
            "source_boundary_record_count", 0
        ),
    )
    _remove_superseded_surface_failures(
        graph,
        replaced_surface_ids,
        replacement_topology=attachment_topology,
    )
    topology_started = time.perf_counter()
    graph["topology_graph"] = build_v10_topology_graph(graph["surfaces"])
    _emit_r16_timing(
        "legacy_topology_graph",
        topology_started,
        edge_record_count=graph["topology_graph"].get("edge_record_count", 0),
    )
    graph["attachment_topology_contract"] = attachment_topology
    graph["source_math_policy"] = "authenticated_step_direct_section_curve_network"
    graph["reconstruction_implementation_revision"] = IMPLEMENTATION_REVISION
    endpoint_witnesses = mapping.get("semantic_endpoint_witnesses")
    common_z_diagnostic = _common_z_boundary_diagnostic(
        graph,
        endpoint_witnesses=endpoint_witnesses,
    )
    if common_z_diagnostic["status"] == "FAIL":
        raise DirectSectionSurfaceError(
            "v116_unexplained_common_z_cutoff",
            "unrelated hub, blade-side and root boundaries share an unsupported Z plane",
            common_z_diagnostic,
        )
    graph["direct_section_curve_network"] = {
        "contract_id": network["contract_id"],
        "implementation_revision": IMPLEMENTATION_REVISION,
        "construction_usage": "step_reconstruction_only",
        "populations": population_manifests,
        "generated_section_loops": generated_loops,
        "semantic_endpoint_witnesses": copy.deepcopy(endpoint_witnesses),
        "common_z_boundary_diagnostic": common_z_diagnostic,
        "attachment_topology_contract": copy.deepcopy(attachment_topology),
    }
    if isinstance(graph.get("parameter_inspection"), Mapping):
        inspection_started = time.perf_counter()
        inspection = build_parameter_inspection_contract(graph)
        graph["generation_id"] = inspection["generation_id"]
        graph["parameter_inspection"] = inspection
        _emit_r16_timing("parameter_inspection", inspection_started)
    _emit_r16_timing("direct_surface_replacement_total", total_started)
    return graph, copy.deepcopy(graph["direct_section_curve_network"])


def _copy_surface_graph_for_direct_replacement(
    surface_graph: Mapping[str, Any],
) -> dict[str, Any]:
    graph = dict(surface_graph)
    graph["surfaces"] = []
    for raw_surface in surface_graph.get("surfaces", ()):
        surface = dict(raw_surface)
        display = raw_surface.get("display")
        if isinstance(display, Mapping):
            surface["display"] = copy.deepcopy(dict(display))
        graph["surfaces"].append(surface)
    graph["transition_failures"] = copy.deepcopy(
        list(surface_graph.get("transition_failures", ()) or ())
    )
    return graph


def _emit_r16_timing(
    label: str,
    started: float,
    **counts: Any,
) -> None:
    if os.environ.get("V116_R16_DIAGNOSTIC_TIMING") != "1":
        return
    elapsed = time.perf_counter() - started
    suffix = " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    message = (
        f"V116_R16_TIMING label={label} elapsed_s={elapsed:.6f} {suffix}".rstrip()
    )
    try:
        print(message, flush=True)
    except OSError:
        # Diagnostic output must not abort a detached audit worker.
        pass
    path = os.environ.get("V116_R16_DIAGNOSTIC_TIMING_PATH")
    if path:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(message + "\n")


def _common_z_boundary_diagnostic(
    graph: Mapping[str, Any],
    *,
    endpoint_witnesses: Any = None,
) -> dict[str, Any]:
    tolerance = 0.05
    if isinstance(endpoint_witnesses, Mapping):
        tolerance = max(
            tolerance,
            2.0 * float(endpoint_witnesses.get("source_tolerance_mm", 0.0)),
        )
    candidates = []
    for surface in graph.get("surfaces", ()):
        category = _common_z_surface_category(surface)
        if category is None:
            continue
        points = np.asarray(surface.get("uv_grid"), dtype=float)
        if (
            points.ndim != 3
            or points.shape[0] < 2
            or points.shape[1] < 2
            or points.shape[2] != 3
            or np.any(~np.isfinite(points))
        ):
            continue
        boundaries = {
            "row_start": points[0],
            "row_end": points[-1],
            "column_start": points[:, 0],
            "column_end": points[:, -1],
        }
        for boundary_name, boundary in boundaries.items():
            z_values = boundary[:, 2]
            if float(np.ptp(z_values)) > tolerance:
                continue
            candidates.append(
                {
                    "surface_id": str(surface.get("id", "")),
                    "role": str(surface.get("role", "")),
                    "category": category,
                    "boundary": boundary_name,
                    "canonical_z_mm": float(np.mean(z_values)),
                    "z_spread_mm": float(np.ptp(z_values)),
                }
            )

    clusters = []
    for candidate in sorted(candidates, key=lambda item: item["canonical_z_mm"]):
        cluster = next(
            (
                item
                for item in clusters
                if abs(
                    float(item["canonical_z_mm"])
                    - float(candidate["canonical_z_mm"])
                )
                <= tolerance
            ),
            None,
        )
        if cluster is None:
            cluster = {
                "canonical_z_mm": float(candidate["canonical_z_mm"]),
                "members": [],
            }
            clusters.append(cluster)
        cluster["members"].append(candidate)
        cluster["canonical_z_mm"] = float(
            np.mean([member["canonical_z_mm"] for member in cluster["members"]])
        )

    unexplained = []
    for cluster in clusters:
        categories = sorted({member["category"] for member in cluster["members"]})
        cluster["categories"] = categories
        cluster["source_explanation"] = _common_z_source_explanation(
            float(cluster["canonical_z_mm"]),
            endpoint_witnesses,
            tolerance,
        )
        if (
            {"hub", "blade_side", "root_attachment"}.issubset(categories)
            and cluster["source_explanation"] is None
        ):
            unexplained.append(copy.deepcopy(cluster))
    return {
        "contract_id": "impeller_v1_1_6_common_z_boundary_gate_r16_1",
        "coordinate_frame": "canonical_axis_frame_xyz_mm",
        "tolerance_mm": float(tolerance),
        "candidate_boundary_count": len(candidates),
        "clusters": clusters,
        "unexplained_common_z_clusters": unexplained,
        "status": "FAIL" if unexplained else "PASS",
    }


def _common_z_surface_category(surface: Mapping[str, Any]) -> str | None:
    role = str(surface.get("role", ""))
    surface_id = str(surface.get("id", ""))
    if role in {"blade_pressure", "blade_suction"}:
        return "blade_side"
    if role == "root_to_hub_attachment":
        return "root_attachment"
    if (
        role in {
            "hub",
            "outer_hub_shell",
            "inner_hub_bottom",
            "mounting_bore",
            "hub_material_closure",
        }
        or "hub_" in surface_id
        or surface_id.startswith("hub")
    ):
        return "hub"
    return None


def _common_z_source_explanation(
    canonical_z_mm: float,
    endpoint_witnesses: Any,
    tolerance_mm: float,
) -> str | None:
    if not isinstance(endpoint_witnesses, Mapping):
        return None
    blade = endpoint_witnesses.get("blade_leading_boundary", {})
    blade_range = np.asarray(blade.get("canonical_z_range_mm"), dtype=float)
    if (
        blade_range.shape == (2,)
        and np.all(np.isfinite(blade_range))
        and float(np.ptp(blade_range)) <= tolerance_mm
        and float(blade_range[0]) - tolerance_mm
        <= canonical_z_mm
        <= float(blade_range[1]) + tolerance_mm
    ):
        return "authenticated_source_blade_leading_boundary_is_planar"
    return None


def _build_population_grids(
    stations: Sequence[Mapping[str, Any]],
    *,
    span_sample_count: int,
    curve_sample_count: int,
    native_source_stream_sampling: bool = False,
) -> tuple[dict[str, list[list[list[float]]]], dict[str, Any]]:
    if len(stations) < 3:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_station_count_invalid",
            "direct curve loft requires at least three authoritative stations",
        )
    station_h = np.asarray([float(station["active_h"]) for station in stations], dtype=float)
    if station_h[0] != 0.0 or station_h[-1] != 1.0 or np.any(np.diff(station_h) <= 0.0):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_station_order_invalid",
            "direct curve stations must be unique and span active h=0 through h=1",
        )
    requested_span = np.linspace(0.0, 1.0, max(int(span_sample_count), len(stations)))
    span_h = np.asarray(sorted(set(requested_span.tolist() + station_h.tolist())), dtype=float)
    roles = set(stations[0]["curves"])
    if not {"side_a", "side_b"}.issubset(roles):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_role_invalid",
            "direct curve network lacks independent side_a and side_b curves",
        )
    if any(set(station["curves"]) != roles for station in stations):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_role_invalid",
            "all direct curve stations must expose the same curve roles",
        )
    side_correspondence = {
        role: _source_face_correspondence(stations, role)
        for role in sorted(roles.intersection({"side_a", "side_b"}))
    }
    exact_side_surfaces = {
        role: _common_source_surface_authority(stations, role)
        for role in sorted(roles.intersection({"side_a", "side_b"}))
    }
    exact_trim_side_authority = all(
        isinstance(exact_side_surfaces.get(role), Mapping)
        and exact_side_surfaces[role].get("trim_boundary_uv_paths")
        for role in ("side_a", "side_b")
    )
    if exact_trim_side_authority:
        side_queries = {role: None for role in ("side_a", "side_b")}
    else:
        common_query_values = {
            *np.linspace(
                0.0, 1.0, max(17, int(curve_sample_count))
            ).tolist()
        }
        common_query_values.update(
            round(float(value), 12)
            for parameters, _evidence in side_correspondence.values()
            if parameters is not None
            for station_parameters in parameters
            for value in station_parameters
        )
        common_side_query = np.asarray(sorted(common_query_values), dtype=float)
        side_queries = {
            role: common_side_query for role in ("side_a", "side_b")
        }
    grids = {}
    correspondence_evidence = {}
    exact_source_trim_roles = []
    station_surface_incidence_residuals = {}
    for role in sorted(roles):
        correspondence_parameters, role_correspondence = (
            side_correspondence[role]
            if role in {"side_a", "side_b"}
            else (None, {"method": "curve_local_parameter"})
        )
        curve_query = (
            side_queries[role]
            if role in {"side_a", "side_b"}
            and side_queries[role] is not None
            else np.linspace(0.0, 1.0, max(17, int(curve_sample_count)))
        )
        sample_count = len(curve_query)
        source_surface = exact_side_surfaces.get(role)
        if source_surface is not None:
            if correspondence_parameters is None:
                raise DirectSectionSurfaceError(
                    "v116_direct_curve_correspondence_invalid",
                    f"{role} source surface lacks source-face curve parameters",
                )
            sampled_uv, trim_evidence = _source_trim_parameter_grid(
                source_surface,
                stations,
                role,
                role_correspondence,
                span_h,
                curve_sample_count=max(17, int(curve_sample_count)),
            )
            incidence_residual = _source_face_station_incidence_residual_max_mm(
                stations,
                role,
                source_surface,
            )
            station_surface_incidence_residuals[role] = incidence_residual
            role_correspondence = {
                **role_correspondence,
                **trim_evidence,
                "station_curve_usage": (
                    "authoritative_analytic_surface_incidence_constraint"
                ),
                "station_surface_incidence_residual_max_mm": incidence_residual,
            }
            exact_source_trim_roles.append(role)
            sampled = _evaluate_source_face_surface(source_surface, sampled_uv)
            role_correspondence = {
                **role_correspondence,
                "surface_evaluation": (
                    "authenticated_source_nurbs_evaluated_from_trimmed_parameter_domain"
                ),
            }
        else:
            rows = np.asarray(
                [
                    _resample_authoritative_curve(
                        station["curves"][role],
                        role,
                        sample_count,
                        query=curve_query,
                        correspondence_parameter=(
                            None
                            if correspondence_parameters is None
                            else correspondence_parameters[index]
                        ),
                    )
                    for index, station in enumerate(stations)
                ],
                dtype=float,
            )
            spline = PchipInterpolator(station_h, rows, axis=0)
            sampled = np.asarray(spline(span_h), dtype=float)
            for index, h in enumerate(station_h):
                sampled[int(np.argmin(np.abs(span_h - h)))] = rows[index]
        if np.any(~np.isfinite(sampled)):
            raise DirectSectionSurfaceError(
                "v116_direct_curve_surface_invalid",
                f"{role} direct curve loft produced non-finite points",
            )
        grids[role] = sampled.tolist()
        correspondence_evidence[role] = role_correspondence
    if (
        _closure_mode(stations) == "sharp_shared_seam"
        and set(exact_source_trim_roles) == {"side_a", "side_b"}
    ):
        side_a = np.asarray(grids["side_a"], dtype=float)
        side_b = np.asarray(grids["side_b"], dtype=float)
        grids["leading_edge"] = np.linspace(
            side_b[:, 0], side_a[:, 0], 3, axis=1
        ).tolist()
        grids["trailing_edge"] = np.linspace(
            side_a[:, -1], side_b[:, -1], 3, axis=1
        ).tolist()
        correspondence_evidence["leading_edge"] = {
            "method": "shared_trim_boundary_topology",
            "closure_classification": "sharp_shared_seam",
        }
        correspondence_evidence["trailing_edge"] = {
            "method": "shared_trim_boundary_topology",
            "closure_classification": "sharp_shared_seam",
        }
    return grids, {
        "span_samples_h": span_h.tolist(),
        "surface_correspondence": correspondence_evidence,
        "exact_source_trim_roles": sorted(exact_source_trim_roles),
        "station_surface_incidence_residual_max_mm": max(
            station_surface_incidence_residuals.values(), default=math.inf
        ),
    }


def _source_face_correspondence(
    stations: Sequence[Mapping[str, Any]], role: str
) -> tuple[list[np.ndarray] | None, dict[str, Any]]:
    records = [station["curves"][role].get("source_face_parameter") for station in stations]
    present = [isinstance(record, Mapping) for record in records]
    if not any(present):
        return None, {
            "method": "compatibility_local_curve_chord_parameter",
            "source_parameter_available": False,
        }
    if not all(present):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            f"{role} source-face parameter authority is missing at some stations",
            {
                "role": role,
                "available_station_indices": [
                    index for index, available in enumerate(present) if available
                ],
                "station_count": len(stations),
            },
        )
    typed_records = [record for record in records if isinstance(record, Mapping)]
    face_ids = {str(record.get("face_id", "")) for record in typed_records}
    if len(face_ids) != 1 or "" in face_ids:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            f"{role} stations do not share one authenticated source face",
            {"role": role, "source_face_ids": sorted(face_ids)},
        )
    uv_samples = []
    residuals = []
    for index, (station, record) in enumerate(zip(stations, typed_records, strict=True)):
        uv = np.asarray(record.get("uv"), dtype=float)
        point_count = len(station["curves"][role]["canonical_points_xyz_mm"])
        if (
            uv.shape != (point_count, 2)
            or np.any(~np.isfinite(uv))
            or point_count < 2
        ):
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                f"{role} source-face UV witnesses do not match curve samples",
                {
                    "role": role,
                    "station_index": index,
                    "uv_shape": list(uv.shape),
                    "curve_point_count": point_count,
                },
            )
        uv_samples.append(uv)
        residuals.append(float(record.get("projection_residual_max_mm", 0.0)))

    candidates = []
    for axis in (0, 1):
        parameters = []
        station_evidence = []
        valid = True
        for uv in uv_samples:
            values = np.asarray(uv[:, axis], dtype=float)
            endpoint_delta = float(values[-1] - values[0])
            if abs(endpoint_delta) <= 1.0e-12:
                valid = False
                station_evidence.append(
                    {"endpoint_delta": endpoint_delta, "reason": "zero_endpoint_span"}
                )
                continue
            normalized = (values - values[0]) / endpoint_delta
            differences = np.diff(normalized)
            backward_extent = float(np.sum(np.maximum(-differences, 0.0)))
            maximum_backward_step = float(max(0.0, -np.min(differences)))
            allowed_backward_extent = max(0.01, 8.0 / max(len(values) - 1, 1))
            allowed_backward_step = max(0.005, 2.0 / max(len(values) - 1, 1))
            if (
                backward_extent > allowed_backward_extent
                or maximum_backward_step > allowed_backward_step
            ):
                valid = False
            repaired, isotonic_adjustment = _source_domain_parameter(
                normalized, uv
            )
            parameters.append(repaired)
            station_evidence.append(
                {
                    "endpoint_delta": endpoint_delta,
                    "backward_extent": backward_extent,
                    "maximum_backward_step": maximum_backward_step,
                    "allowed_backward_extent": allowed_backward_extent,
                    "allowed_backward_step": allowed_backward_step,
                    "isotonic_adjustment_max": isotonic_adjustment,
                }
            )
        candidates.append(
            {
                "axis": axis,
                "valid": valid and len(parameters) == len(stations),
                "parameters": parameters,
                "station_evidence": station_evidence,
                "median_endpoint_span": float(
                    np.median(
                        [
                            abs(float(uv[-1, axis] - uv[0, axis]))
                            for uv in uv_samples
                        ]
                    )
                ),
            }
        )
    valid_candidates = [candidate for candidate in candidates if candidate["valid"]]
    if not valid_candidates:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            f"{role} has no monotone source-face parameter across the station family",
            {
                "role": role,
                "source_face_id": next(iter(face_ids)),
                "axis_candidates": [
                    {
                        key: value
                        for key, value in candidate.items()
                        if key != "parameters"
                    }
                    for candidate in candidates
                ],
            },
        )
    selected = max(
        valid_candidates,
        key=lambda candidate: (candidate["median_endpoint_span"], -candidate["axis"]),
    )
    return selected["parameters"], {
        "method": "authenticated_source_face_native_parameter",
        "source_parameter_available": True,
        "source_face_id": next(iter(face_ids)),
        "source_parameter_axis": "u" if selected["axis"] == 0 else "v",
        "station_normalization": (
            "source_face_endpoint_normalized_isotonic_with_uv_arc_tie_break"
        ),
        "projection_residual_max_mm": max(residuals, default=0.0),
        "station_evidence": selected["station_evidence"],
    }


def _common_source_surface_authority(
    stations: Sequence[Mapping[str, Any]], role: str
) -> Mapping[str, Any] | None:
    records = [station["curves"][role].get("source_face_surface") for station in stations]
    present = [isinstance(record, Mapping) for record in records]
    if not any(present):
        return None
    if not all(present):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            f"{role} source-surface authority is missing at some stations",
        )
    typed = [record for record in records if isinstance(record, Mapping)]
    first = typed[0]
    scalar_keys = (
        "source_face_id",
        "u_degree",
        "v_degree",
        "u_knots",
        "v_knots",
        "u_multiplicities",
        "v_multiplicities",
    )
    for index, record in enumerate(typed[1:], start=1):
        if (
            any(record.get(key) != first.get(key) for key in scalar_keys)
            or record.get("trim_boundary_uv_paths")
            != first.get("trim_boundary_uv_paths")
            or not (
            np.allclose(
                np.asarray(record.get("canonical_control_points_xyz_mm"), dtype=float),
                np.asarray(first.get("canonical_control_points_xyz_mm"), dtype=float),
                atol=1.0e-10,
                rtol=0.0,
            )
            and np.allclose(
                np.asarray(record.get("weights"), dtype=float),
                np.asarray(first.get("weights"), dtype=float),
                atol=1.0e-12,
                rtol=0.0,
            )
            )
        ):
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                f"{role} stations disagree on source NURBS surface authority",
                {"station_index": index},
            )
    return first


def _source_trim_parameter_grid(
    authority: Mapping[str, Any],
    stations: Sequence[Mapping[str, Any]],
    role: str,
    correspondence: Mapping[str, Any],
    span_h: np.ndarray,
    *,
    curve_sample_count: int,
    normalized_stream_query: np.ndarray | None = None,
    normalized_stream_query_authority: str | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    parameter_axis = str(correspondence.get("source_parameter_axis", ""))
    if parameter_axis not in {"u", "v"}:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            f"{role} trimmed source surface lacks a streamwise parameter axis",
        )
    stream_axis = 0 if parameter_axis == "u" else 1
    span_axis = 1 - stream_axis
    station_uv = []
    for station in stations:
        record = station["curves"][role].get("source_face_parameter")
        uv = np.asarray(record.get("uv") if isinstance(record, Mapping) else (), dtype=float)
        if uv.ndim != 2 or uv.shape[1] != 2 or len(uv) < 2:
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                f"{role} station lacks source UV witnesses for trim orientation",
            )
        station_uv.append(uv)
    stream_start = float(np.median([uv[0, stream_axis] for uv in station_uv]))
    stream_end = float(np.median([uv[-1, stream_axis] for uv in station_uv]))
    if abs(stream_end - stream_start) <= 1.0e-12:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            f"{role} source trim has zero streamwise extent",
        )
    paths = _trim_boundary_paths(authority)
    path_stream = np.concatenate([path[:, stream_axis] for path in paths])
    stream_min = float(np.min(path_stream))
    stream_max = float(np.max(path_stream))
    stream_start = float(np.clip(stream_start, stream_min, stream_max))
    stream_end = float(np.clip(stream_end, stream_min, stream_max))
    if normalized_stream_query is None:
        stream_values = _source_trim_stream_values(
            authority,
            stream_axis=stream_axis,
            stream_start=stream_start,
            stream_end=stream_end,
            minimum_sample_count=curve_sample_count,
        )
        stream_query_authority = "source_surface_native_knots_and_uniform_samples"
    else:
        normalized = np.asarray(normalized_stream_query, dtype=float)
        if (
            normalized.ndim != 1
            or len(normalized) < 2
            or np.any(~np.isfinite(normalized))
            or np.any(np.diff(normalized) <= 0.0)
            or normalized[0] < -1.0e-12
            or normalized[-1] > 1.0 + 1.0e-12
        ):
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                f"{role} common normalized stream query is invalid",
            )
        stream_values = stream_start + normalized * (stream_end - stream_start)
        stream_query_authority = str(
            normalized_stream_query_authority
            or "caller_supplied_normalized_source_parameter_query"
        )
    lower = []
    upper = []
    for stream_value in stream_values:
        intersections = _trim_span_intersections(
            paths,
            stream_axis=stream_axis,
            span_axis=span_axis,
            stream_value=float(stream_value),
        )
        if len(intersections) < 2:
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                f"{role} source trim is not a bounded strip",
                {
                    "stream_value": float(stream_value),
                    "intersection_count": len(intersections),
                },
            )
        lower.append(float(min(intersections)))
        upper.append(float(max(intersections)))
    lower_values = np.asarray(lower, dtype=float)
    upper_values = np.asarray(upper, dtype=float)
    if np.any(upper_values - lower_values <= 1.0e-10):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            f"{role} source trim span collapses or reverses",
        )
    first_span = float(np.median(station_uv[0][:, span_axis]))
    lower_distance = float(np.median(np.abs(first_span - lower_values)))
    upper_distance = float(np.median(np.abs(first_span - upper_values)))
    root_values, tip_values = (
        (lower_values, upper_values)
        if lower_distance <= upper_distance
        else (upper_values, lower_values)
    )
    span_values = (
        root_values[None, :]
        + np.asarray(span_h, dtype=float)[:, None]
        * (tip_values - root_values)[None, :]
    )
    uv_grid = np.empty((len(span_h), len(stream_values), 2), dtype=float)
    uv_grid[:, :, stream_axis] = stream_values[None, :]
    uv_grid[:, :, span_axis] = span_values
    return uv_grid, {
        "method": "authenticated_source_face_trimmed_parameter_domain",
        "trim_boundary_path_count": len(paths),
        "trim_streamwise_parameter_range": [stream_start, stream_end],
        "trim_span_width_min": float(np.min(np.abs(tip_values - root_values))),
        "stream_query_authority": stream_query_authority,
        "stream_sample_count": len(stream_values),
        "station_curve_usage": "measurement_and_validation_not_surface_authority",
    }


def _uv_grid_trim_domain_evidence(
    authority: Mapping[str, Any], uv_grid: np.ndarray
) -> dict[str, Any]:
    paths = _ordered_closed_trim_paths(_trim_boundary_paths(authority))
    polygon = np.vstack(
        [_resample_polyline(path, 129)[:-1] for path in paths]
    )
    scale = max(float(np.ptp(polygon, axis=0).max()), 1.0e-6)
    tolerance = max(1.0e-8, 5.0e-5 * scale)
    outside = []
    for row_index, row in enumerate(np.asarray(uv_grid, dtype=float)):
        for column_index, point in enumerate(row):
            if _point_inside_trim_polygon(point, polygon):
                continue
            distance = _point_to_polyline_distance(point, polygon)
            if distance <= tolerance:
                continue
            outside.append(
                {
                    "row_index": row_index,
                    "column_index": column_index,
                    "trim_distance": distance,
                }
            )
    maximum_distance = max(
        (float(record["trim_distance"]) for record in outside),
        default=0.0,
    )
    return {
        "status": "PASS" if not outside else "FAIL",
        "trim_boundary_path_count": len(paths),
        "trim_domain_sample_count": int(np.prod(uv_grid.shape[:2])),
        "trim_domain_outside_sample_count": len(outside),
        "trim_domain_maximum_outside_distance": maximum_distance,
        "trim_domain_tolerance": tolerance,
        "trim_domain_failures": outside[:16],
    }


def _physical_arc_correspondence_queries(
    stations: Sequence[Mapping[str, Any]],
    side_correspondence: Mapping[
        str, tuple[list[np.ndarray] | None, Mapping[str, Any]]
    ],
    *,
    sample_count: int,
) -> dict[str, np.ndarray]:
    physical_query = np.linspace(0.0, 1.0, max(17, int(sample_count)))
    result = {}
    for role in ("side_a", "side_b"):
        parameters, _evidence = side_correspondence[role]
        if parameters is None or len(parameters) != len(stations):
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                f"{role} lacks station source parameters for physical correspondence",
            )
        station_queries = []
        for station, source_parameter in zip(stations, parameters, strict=True):
            points = np.asarray(
                station["curves"][role]["canonical_points_xyz_mm"], dtype=float
            )
            source_parameter = np.asarray(source_parameter, dtype=float)
            if len(points) != len(source_parameter):
                raise DirectSectionSurfaceError(
                    "v116_direct_curve_correspondence_invalid",
                    f"{role} physical curve and source parameter counts differ",
                )
            lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
            physical = np.concatenate([[0.0], np.cumsum(lengths)])
            if physical[-1] <= 1.0e-12:
                raise DirectSectionSurfaceError(
                    "v116_direct_curve_correspondence_invalid",
                    f"{role} station curve has zero physical length",
                )
            physical /= physical[-1]
            keep = np.concatenate([[True], np.diff(physical) > 1.0e-12])
            station_queries.append(
                np.interp(
                    physical_query,
                    physical[keep],
                    source_parameter[keep],
                )
            )
        query = np.median(np.asarray(station_queries, dtype=float), axis=0)
        query = _isotonic_non_decreasing(query)
        span = float(query[-1] - query[0])
        if span <= 1.0e-12:
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                f"{role} physical-to-source correspondence collapsed",
            )
        query = (query - query[0]) / span
        query[0] = 0.0
        query[-1] = 1.0
        if np.any(np.diff(query) <= 0.0):
            query += np.linspace(0.0, 1.0e-9, len(query))
            query = (query - query[0]) / (query[-1] - query[0])
        result[role] = query
    return result


def _source_trim_stream_values(
    authority: Mapping[str, Any],
    *,
    stream_axis: int,
    stream_start: float,
    stream_end: float,
    minimum_sample_count: int,
) -> np.ndarray:
    key = "u_knots" if stream_axis == 0 else "v_knots"
    knots = np.asarray(authority.get(key), dtype=float)
    lower = min(stream_start, stream_end)
    upper = max(stream_start, stream_end)
    retained_knots = knots[(knots >= lower) & (knots <= upper)]
    values = {
        *np.linspace(stream_start, stream_end, minimum_sample_count).tolist(),
        *retained_knots.tolist(),
        stream_start,
        stream_end,
    }
    ordered = sorted(values, reverse=stream_start > stream_end)
    parameter_tolerance = max(
        1.0e-10,
        1.0e-6 * max(abs(stream_end - stream_start), 1.0e-6),
    )
    unique = []
    for value in ordered:
        if not unique or abs(value - unique[-1]) > parameter_tolerance:
            unique.append(float(value))
    return np.asarray(unique, dtype=float)


def _trim_boundary_paths(authority: Mapping[str, Any]) -> list[np.ndarray]:
    records = authority.get("trim_boundary_uv_paths")
    if not isinstance(records, Sequence):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS surface lacks trim-boundary paths",
        )
    paths = []
    for record in records:
        uv = np.asarray(record.get("uv") if isinstance(record, Mapping) else (), dtype=float)
        if uv.ndim != 2 or uv.shape[1] != 2 or len(uv) < 2 or np.any(~np.isfinite(uv)):
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                "source NURBS trim boundary is invalid",
            )
        paths.append(uv)
    if len(paths) < 3:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS face does not expose a closed trim-boundary inventory",
            {"trim_boundary_path_count": len(paths)},
        )
    return paths


def _trim_span_intersections(
    paths: Sequence[np.ndarray],
    *,
    stream_axis: int,
    span_axis: int,
    stream_value: float,
) -> list[float]:
    stream_range = float(
        np.ptp(np.concatenate([path[:, stream_axis] for path in paths]))
    )
    scale = max(stream_range, 1.0e-6)
    tolerance = max(1.0e-8, 1.0e-9 * scale)
    constant_path_tolerance = max(1.0e-8, 5.0e-4 * scale)
    values = []
    for path in paths:
        path_stream = path[:, stream_axis]
        if float(np.ptp(path_stream)) <= constant_path_tolerance:
            if (
                float(np.min(path_stream)) - constant_path_tolerance
                <= stream_value
                <= float(np.max(path_stream)) + constant_path_tolerance
            ):
                values.extend(float(value) for value in path[:, span_axis])
            continue
        for first, second in zip(path[:-1], path[1:], strict=True):
            first_stream = float(first[stream_axis])
            second_stream = float(second[stream_axis])
            delta = second_stream - first_stream
            if abs(delta) <= tolerance:
                if abs(stream_value - first_stream) <= tolerance:
                    values.extend([float(first[span_axis]), float(second[span_axis])])
                continue
            parameter = (stream_value - first_stream) / delta
            if -tolerance <= parameter <= 1.0 + tolerance:
                bounded = float(np.clip(parameter, 0.0, 1.0))
                values.append(
                    float(first[span_axis] + bounded * (second[span_axis] - first[span_axis]))
                )
    ordered = sorted(values)
    unique = []
    for value in ordered:
        if not unique or abs(value - unique[-1]) > tolerance:
            unique.append(value)
    return unique


def _resample_source_face_uv(
    curve: Mapping[str, Any], parameter: np.ndarray, query: np.ndarray
) -> np.ndarray:
    source_parameter = curve.get("source_face_parameter")
    if not isinstance(source_parameter, Mapping):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS evaluation requires source-face UV witnesses",
        )
    uv = np.asarray(source_parameter.get("uv"), dtype=float)
    values = np.asarray(parameter, dtype=float)
    if (
        uv.ndim != 2
        or uv.shape[1] != 2
        or len(uv) != len(values)
        or np.any(~np.isfinite(uv))
        or np.any(np.diff(values) <= 0.0)
    ):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source-face UV path is incompatible with its correspondence parameter",
        )
    query = np.asarray(query, dtype=float)
    return np.column_stack(
        [np.interp(query, values, uv[:, axis]) for axis in range(2)]
    )


def _source_face_station_incidence_residual_max_mm(
    stations: Sequence[Mapping[str, Any]],
    role: str,
    authority: Mapping[str, Any],
) -> float:
    maximum = 0.0
    for station_index, station in enumerate(stations):
        curve = station["curves"][role]
        parameter = curve.get("source_face_parameter")
        if not isinstance(parameter, Mapping):
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                f"{role} station lacks source-face UV witnesses",
                {"role": role, "station_index": station_index},
            )
        uv = np.asarray(parameter.get("uv"), dtype=float)
        expected = np.asarray(curve.get("canonical_points_xyz_mm"), dtype=float)
        if uv.shape != (len(expected), 2):
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                f"{role} station UV and canonical curve samples differ",
                {"role": role, "station_index": station_index},
            )
        evaluated = _evaluate_source_face_surface(authority, uv[None, :, :])[0]
        maximum = max(
            maximum,
            float(np.max(np.linalg.norm(evaluated - expected, axis=1))),
        )
    return maximum


def _evaluate_source_face_surface(
    authority: Mapping[str, Any], uv_grid: np.ndarray
) -> np.ndarray:
    controls = np.asarray(authority.get("canonical_control_points_xyz_mm"), dtype=float)
    weights = np.asarray(authority.get("weights"), dtype=float)
    if (
        controls.ndim != 3
        or controls.shape[2] != 3
        or weights.shape != controls.shape[:2]
        or np.any(~np.isfinite(controls))
        or np.any(~np.isfinite(weights))
        or np.any(weights <= 0.0)
    ):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS control net is invalid",
        )
    u_degree = int(authority["u_degree"])
    v_degree = int(authority["v_degree"])
    u_knots = np.repeat(
        np.asarray(authority["u_knots"], dtype=float),
        np.asarray(authority["u_multiplicities"], dtype=int),
    )
    v_knots = np.repeat(
        np.asarray(authority["v_knots"], dtype=float),
        np.asarray(authority["v_multiplicities"], dtype=int),
    )
    if (
        len(u_knots) - u_degree - 1 != controls.shape[0]
        or len(v_knots) - v_degree - 1 != controls.shape[1]
    ):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS knots do not match the control net",
        )
    uv = np.asarray(uv_grid, dtype=float)
    flat = uv.reshape(-1, 2)
    u_values = np.clip(flat[:, 0], u_knots[u_degree], u_knots[-u_degree - 1])
    v_values = np.clip(flat[:, 1], v_knots[v_degree], v_knots[-v_degree - 1])
    u_basis = BSpline.design_matrix(
        u_values, u_knots, u_degree, extrapolate=False
    ).toarray()
    v_basis = BSpline.design_matrix(
        v_values, v_knots, v_degree, extrapolate=False
    ).toarray()
    numerator = np.einsum(
        "pi,pj,ij,ijc->pc",
        u_basis,
        v_basis,
        weights,
        controls,
        optimize=True,
    )
    denominator = np.einsum(
        "pi,pj,ij->p", u_basis, v_basis, weights, optimize=True
    )
    if np.any(denominator <= 1.0e-15):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS evaluation produced a zero rational denominator",
        )
    return (numerator / denominator[:, None]).reshape((*uv.shape[:-1], 3))


def _source_domain_parameter(
    values: np.ndarray, uv: np.ndarray
) -> tuple[np.ndarray, float]:
    raw = np.asarray(values, dtype=float)
    isotonic = _isotonic_non_decreasing(raw)
    adjustment = float(np.max(np.abs(isotonic - raw)))
    uv_steps = np.linalg.norm(np.diff(np.asarray(uv, dtype=float), axis=0), axis=1)
    uv_arc = np.concatenate([[0.0], np.cumsum(uv_steps)])
    if uv_arc[-1] <= 1.0e-15:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source-face UV curve has zero parameter-domain length",
        )
    uv_arc /= uv_arc[-1]
    tie_break_weight = 1.0e-6
    result = (1.0 - tie_break_weight) * isotonic + tie_break_weight * uv_arc
    span = float(result[-1] - result[0])
    if span <= 1.0e-15:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source-face correspondence parameter collapsed after normalization",
        )
    result = (result - result[0]) / span
    result[0] = 0.0
    result[-1] = 1.0
    return result, adjustment


def _isotonic_non_decreasing(values: np.ndarray) -> np.ndarray:
    blocks: list[list[float]] = []
    for index, value in enumerate(np.asarray(values, dtype=float)):
        blocks.append([float(value), 1.0, float(index), float(index)])
        while len(blocks) >= 2 and blocks[-2][0] > blocks[-1][0]:
            right = blocks.pop()
            left = blocks.pop()
            weight = left[1] + right[1]
            blocks.append(
                [
                    (left[0] * left[1] + right[0] * right[1]) / weight,
                    weight,
                    left[2],
                    right[3],
                ]
            )
    result = np.empty(len(values), dtype=float)
    for mean, _weight, start, end in blocks:
        result[int(start) : int(end) + 1] = mean
    return np.maximum.accumulate(np.clip(result, 0.0, 1.0))


def _generated_station_loop(
    population: str,
    station: Mapping[str, Any],
    grids: Mapping[str, Sequence[Sequence[Sequence[float]]]],
    span_samples_h: Sequence[float],
    *,
    exact_source_trim_roles: set[str] | None = None,
) -> dict[str, Any]:
    eta = float(station["active_h"])
    exact_roles = set(exact_source_trim_roles or ())
    if exact_roles == {"side_a", "side_b"}:
        rows = {
            role: copy.deepcopy(curve["canonical_points_xyz_mm"])
            for role, curve in station["curves"].items()
        }
        intersection_authority = (
            "authenticated_source_face_uv_witness_curve_validated_on_"
            "reconstructed_trimmed_surface"
        )
    else:
        row_index = int(
            np.argmin(np.abs(np.asarray(span_samples_h, dtype=float) - eta))
        )
        rows = {role: copy.deepcopy(grid[row_index]) for role, grid in grids.items()}
        intersection_authority = "sampled_reconstructed_surface_grid_row"
    closed = [*rows["side_a"]]
    if "trailing_edge" in rows:
        closed.extend(rows["trailing_edge"][1:])
    closed.extend(reversed(rows["side_b"][:-1]))
    if "leading_edge" in rows:
        closed.extend(rows["leading_edge"][1:])
    return {
        "loop_id": f"generated:{population}:h_{eta:.9f}",
        "population": population,
        "active_h": eta,
        "coordinate_frame": "canonical_axis_frame_xyz_mm",
        "authority": "reconstructed_surface_carrier_intersection",
        "intersection_authority": intersection_authority,
        "status": "AVAILABLE",
        "points_xyz_mm": closed,
        "surface_curve_rows": rows,
    }


def _surface_quality(grids: Mapping[str, Sequence[Sequence[Sequence[float]]]]) -> dict[str, Any]:
    minimum_edge = math.inf
    degenerate_quad_count = 0
    row_reversal_count = 0
    span_reversal_count = 0
    normal_flip_count = 0
    role_quality = {}
    for role, grid in grids.items():
        quality = _single_surface_quality(grid)
        role_quality[str(role)] = quality
        minimum_edge = min(minimum_edge, quality["minimum_grid_edge_mm"])
        degenerate_quad_count += quality["degenerate_quad_count"]
        row_reversal_count += quality["row_reversal_count"]
        span_reversal_count += quality["span_reversal_count"]
        normal_flip_count += quality["normal_flip_count"]
    foldover_count = row_reversal_count + span_reversal_count + normal_flip_count
    return {
        "minimum_grid_edge_mm": float(minimum_edge),
        "degenerate_quad_count": degenerate_quad_count,
        "row_reversal_count": row_reversal_count,
        "span_reversal_count": span_reversal_count,
        "normal_flip_count": normal_flip_count,
        "foldover_count": foldover_count,
        "role_quality": role_quality,
        "status": (
            "PASS"
            if minimum_edge > 1.0e-9
            and not degenerate_quad_count
            and not foldover_count
            else "FAIL"
        ),
    }


def _single_surface_quality(
    grid: Sequence[Sequence[Sequence[float]]],
) -> dict[str, Any]:
    points = np.asarray(grid, dtype=float)
    if (
        points.ndim != 3
        or points.shape[0] < 2
        or points.shape[1] < 2
        or points.shape[2] != 3
        or np.any(~np.isfinite(points))
    ):
        return {
            "minimum_grid_edge_mm": 0.0,
            "degenerate_quad_count": 1,
            "row_reversal_count": 0,
            "span_reversal_count": 0,
            "normal_flip_count": 0,
            "foldover_count": 1,
            "status": "FAIL",
        }
    row_vectors = np.diff(points, axis=1)
    span_vectors = np.diff(points, axis=0)
    row_lengths = np.linalg.norm(row_vectors, axis=2)
    span_lengths = np.linalg.norm(span_vectors, axis=2)
    minimum_edge = min(float(np.min(row_lengths)), float(np.min(span_lengths)))
    first = row_vectors[:-1]
    second = span_vectors[:, :-1]
    normals = np.cross(first, second)
    normal_lengths = np.linalg.norm(normals, axis=2)
    degenerate = normal_lengths <= 1.0e-10
    safe_normals = normals / np.maximum(normal_lengths[:, :, None], 1.0e-18)
    row_alignment = np.sum(row_vectors[:-1] * row_vectors[1:], axis=2)
    span_alignment = np.sum(span_vectors[:, :-1] * span_vectors[:, 1:], axis=2)
    normal_alignment = []
    if safe_normals.shape[0] > 1:
        normal_alignment.append(
            np.sum(safe_normals[:-1] * safe_normals[1:], axis=2)
        )
    if safe_normals.shape[1] > 1:
        normal_alignment.append(
            np.sum(safe_normals[:, :-1] * safe_normals[:, 1:], axis=2)
        )
    row_reversals = int(np.count_nonzero(row_alignment <= 0.0))
    span_reversals = int(np.count_nonzero(span_alignment <= 0.0))
    normal_flips = int(
        sum(np.count_nonzero(alignment <= 0.0) for alignment in normal_alignment)
    )
    foldovers = row_reversals + span_reversals + normal_flips
    return {
        "minimum_grid_edge_mm": minimum_edge,
        "degenerate_quad_count": int(np.count_nonzero(degenerate)),
        "row_reversal_count": row_reversals,
        "span_reversal_count": span_reversals,
        "normal_flip_count": normal_flips,
        "foldover_count": foldovers,
        "status": (
            "PASS"
            if minimum_edge > 1.0e-9
            and not np.any(degenerate)
            and not foldovers
            else "FAIL"
        ),
    }


def _authenticated_trim_surface_quality(
    grid: Sequence[Sequence[Sequence[float]]],
    *,
    parameter_grid: Sequence[Sequence[Sequence[float]]] | None = None,
) -> dict[str, Any]:
    quality = _single_surface_quality(grid)
    tangent_rotations = int(
        quality["row_reversal_count"] + quality["span_reversal_count"]
    )
    physical_normal_rotations = int(quality["normal_flip_count"])
    parameter_foldovers = 0
    parameter_degenerate_quads = 0
    minimum_abs_parameter_jacobian = None
    if parameter_grid is not None:
        parameters = np.asarray(parameter_grid, dtype=float)
        if (
            parameters.ndim != 3
            or parameters.shape[:2] != np.asarray(grid).shape[:2]
            or parameters.shape[2] != 2
            or np.any(~np.isfinite(parameters))
        ):
            parameter_degenerate_quads = 1
            minimum_abs_parameter_jacobian = 0.0
        else:
            row_vectors = np.diff(parameters, axis=1)[:-1]
            span_vectors = np.diff(parameters, axis=0)[:, :-1]
            jacobian = (
                row_vectors[:, :, 0] * span_vectors[:, :, 1]
                - row_vectors[:, :, 1] * span_vectors[:, :, 0]
            )
            parameter_scale = max(
                float(np.ptp(parameters[:, :, 0])),
                float(np.ptp(parameters[:, :, 1])),
                1.0e-12,
            )
            parameter_tolerance = 1.0e-12 * parameter_scale * parameter_scale
            minimum_abs_parameter_jacobian = float(np.min(np.abs(jacobian)))
            parameter_degenerate_quads = int(
                np.count_nonzero(np.abs(jacobian) <= parameter_tolerance)
            )
            nonzero = jacobian[np.abs(jacobian) > parameter_tolerance]
            if len(nonzero):
                dominant = 1.0 if float(np.median(nonzero)) > 0.0 else -1.0
                parameter_foldovers = int(np.count_nonzero(dominant * nonzero <= 0.0))
    actual_foldovers = parameter_foldovers
    status = (
        "PASS"
        if quality["minimum_grid_edge_mm"] > 1.0e-9
        and quality["degenerate_quad_count"] == 0
        and parameter_degenerate_quads == 0
        and parameter_foldovers == 0
        else "FAIL"
    )
    return {
        **quality,
        "parameter_tangent_rotation_count": tangent_rotations,
        "physical_normal_rotation_count": physical_normal_rotations,
        "parameterization_checked": parameter_grid is not None,
        "minimum_abs_parameter_jacobian": minimum_abs_parameter_jacobian,
        "parameter_degenerate_quad_count": parameter_degenerate_quads,
        "parameter_foldover_count": parameter_foldovers,
        "foldover_count": actual_foldovers,
        "status": status,
        "foldover_definition": (
            "parameter_domain_jacobian_orientation_failure; physical adjacent "
            "normal rotation and parameter tangent rotation are diagnostic only"
        ),
    }


def _station_residual_max_mm(
    stations: Sequence[Mapping[str, Any]],
    grids: Mapping[str, Sequence[Sequence[Sequence[float]]]],
    span_samples_h: Sequence[float],
) -> float:
    span = np.asarray(span_samples_h, dtype=float)
    maximum = 0.0
    for station in stations:
        row_index = int(np.argmin(np.abs(span - float(station["active_h"]))))
        for role, curve in station["curves"].items():
            expected = np.asarray(curve["canonical_points_xyz_mm"], dtype=float)
            actual = np.asarray(grids[role][row_index], dtype=float)
            maximum = max(
                maximum,
                float(np.max(_points_to_polyline_distances(expected, actual))),
            )
    return maximum


def _points_to_polyline_distances(
    points: np.ndarray, polyline: np.ndarray
) -> np.ndarray:
    starts = np.asarray(polyline[:-1], dtype=float)
    vectors = np.asarray(polyline[1:], dtype=float) - starts
    length_sq = np.sum(vectors * vectors, axis=1)
    result = []
    for point in np.asarray(points, dtype=float):
        offsets = point[None, :] - starts
        parameters = np.divide(
            np.sum(offsets * vectors, axis=1),
            length_sq,
            out=np.zeros_like(length_sq),
            where=length_sq > 1.0e-20,
        )
        parameters = np.clip(parameters, 0.0, 1.0)
        projections = starts + parameters[:, None] * vectors
        result.append(float(np.min(np.linalg.norm(projections - point, axis=1))))
    return np.asarray(result, dtype=float)


def _shared_boundary_gap_max_mm(
    grids: Mapping[str, Sequence[Sequence[Sequence[float]]]],
) -> float:
    required = {"side_a", "side_b", "leading_edge", "trailing_edge"}
    if set(grids) != required:
        return math.inf
    side_a = np.asarray(grids["side_a"], dtype=float)
    side_b = np.asarray(grids["side_b"], dtype=float)
    leading = np.asarray(grids["leading_edge"], dtype=float)
    trailing = np.asarray(grids["trailing_edge"], dtype=float)
    gaps = (
        np.linalg.norm(side_a[:, 0] - leading[:, -1], axis=1),
        np.linalg.norm(side_b[:, 0] - leading[:, 0], axis=1),
        np.linalg.norm(side_a[:, -1] - trailing[:, 0], axis=1),
        np.linalg.norm(side_b[:, -1] - trailing[:, -1], axis=1),
    )
    return float(max(np.max(gap) for gap in gaps))


def _shared_boundary_orientation_mismatch_count(
    grids: Mapping[str, Sequence[Sequence[Sequence[float]]]],
) -> int:
    required = {"side_a", "side_b", "leading_edge", "trailing_edge"}
    if set(grids) != required:
        return 1
    side_a = np.asarray(grids["side_a"], dtype=float)
    side_b = np.asarray(grids["side_b"], dtype=float)
    leading = np.asarray(grids["leading_edge"], dtype=float)
    trailing = np.asarray(grids["trailing_edge"], dtype=float)
    pairs = (
        (side_a[:, 0], leading[:, -1]),
        (side_b[:, 0], leading[:, 0]),
        (side_a[:, -1], trailing[:, 0]),
        (side_b[:, -1], trailing[:, -1]),
    )
    mismatches = 0
    for first_boundary, second_boundary in pairs:
        first_tangent = np.diff(first_boundary, axis=0)
        second_tangent = np.diff(second_boundary, axis=0)
        mismatches += int(
            np.count_nonzero(np.sum(first_tangent * second_tangent, axis=1) <= 0.0)
        )
    return mismatches


def _network(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    provenance = mapping.get("section_provenance")
    if not isinstance(provenance, Mapping):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_contract_missing",
            "mapping lacks section_provenance",
        )
    network = provenance.get("direct_section_curve_network")
    if not isinstance(network, Mapping) or network.get("status") != "PASS":
        raise DirectSectionSurfaceError(
            "v116_direct_curve_contract_missing",
            "mapping lacks a passing direct section curve network",
        )
    if network.get("construction_usage") != "step_reconstruction_only":
        raise DirectSectionSurfaceError(
            "v116_direct_curve_contract_invalid",
            "direct section curves are not authorized for STEP reconstruction",
        )
    return network


def _periodic_populations(mapping: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    periodic = mapping.get("periodic_provenance")
    if not isinstance(periodic, Mapping):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_population_missing",
            "mapping lacks periodic provenance",
        )
    evidence = periodic.get("pattern_population_evidence")
    if not isinstance(evidence, Mapping):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_population_missing",
            "mapping lacks periodic population evidence",
        )
    return {
        str(population["classification"]): population
        for population in evidence.get("populations", ())
    }


def _surface_index(graph: Mapping[str, Any]) -> dict[tuple[str, int, str], dict[str, Any]]:
    surfaces = graph.get("surfaces")
    if not isinstance(surfaces, list):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_surface_missing",
            "surface graph has no mutable surface inventory",
        )
    result = {}
    for surface in surfaces:
        blade_class = surface.get("blade_class")
        role = surface.get("role")
        index = surface.get("blade_pair_index")
        if blade_class is None or role is None:
            continue
        result[(str(blade_class), int(index), str(role))] = surface
    return result


def _replace_attachment_surfaces(
    surface_inventory: list[dict[str, Any]],
    surfaces: Mapping[tuple[str, int, str], dict[str, Any]],
    population: str,
    index: int,
    base_grids: Mapping[str, Sequence[Sequence[Sequence[float]]]],
    transformed_grids: Mapping[str, Sequence[Sequence[Sequence[float]]]],
    stations: Sequence[Mapping[str, Any]],
    active_span_authority: Any,
    transform: np.ndarray,
    *,
    exact_patch_templates: Mapping[str, Sequence[_ExactPatchTemplate]] | None = None,
) -> list[str]:
    replaced = []
    templates = dict(exact_patch_templates or {})
    root_surface = surfaces.get((population, index, "root_to_hub_attachment"))
    if root_surface is not None:
        authority = _active_span_authority(active_span_authority)
        exact_root_patches = authority.get("root_surface_patches")
        if isinstance(exact_root_patches, list) and exact_root_patches:
            replaced.extend(
                _replace_exact_root_patch_surfaces(
                    surface_inventory,
                    root_surface,
                    exact_root_patches,
                    transform,
                    sampled_patches=templates.get("root"),
                )
            )
        else:
            root_loop = _closed_loop_from_grids(base_grids, 0)
            support_loop = _support_loop_from_carrier(
                root_loop,
                stations[0]["support_profile_rz_mm"],
                authority["hub_points_rz_mm"],
            )
            root_rows = _transform_grid(
                _attachment_rows(support_loop, root_loop, row_count=25),
                transform,
            )
            _replace_attachment_surface(
                root_surface,
                root_rows,
                construction="direct_hub_to_measurement_carrier",
                boundary_names=("hub_attachment_loop", "blade_root_loop"),
            )
            root_surface["source"].update(
                {
                    "retained_boundary_authority": authority.get(
                        "root_boundary_authority",
                        "source_retained_blade_boundary_support_envelope",
                    ),
                    "retained_boundary_geometry_usage": (
                        "evidence_only_pending_role_resolved_closed_boundary"
                    ),
                    "measurement_carrier_separated_from_retained_boundary": bool(
                        authority.get("root_carrier_clearance_mm")
                    ),
                }
            )
            root_surface["v1_1_root_quality"] = _direct_root_quality(
                root_rows,
                construction="direct_hub_to_measurement_carrier",
            )
            replaced.append(str(root_surface["id"]))

    open_tip = surfaces.get((population, index, "open_tip_dome"))
    if open_tip is not None:
        authority = _active_span_authority(active_span_authority)
        exact_tip_patches = authority.get("tip_surface_patches")
        if isinstance(exact_tip_patches, list) and exact_tip_patches:
            replaced.extend(
                _replace_exact_tip_patch_surfaces(
                    surface_inventory,
                    open_tip,
                    exact_tip_patches,
                    transform,
                    sampled_patches=templates.get("tip"),
                )
            )
        else:
            tip_grid = _coons_tip_grid(transformed_grids, -1)
            _replace_attachment_surface(
                open_tip,
                tip_grid,
                construction="direct_terminal_section_coons_tip_cap",
                boundary_names=("side_a_tip", "side_b_tip"),
            )
            open_tip["v1_1_tip_quality"] = _direct_tip_quality(
                tip_grid,
                construction="direct_terminal_section_coons_tip_cap",
            )
            replaced.append(str(open_tip["id"]))

    closed_tip = surfaces.get((population, index, "closed_shroud_attachment"))
    if closed_tip is not None:
        authority = _active_span_authority(active_span_authority)
        tip_support = authority.get("tip_points_rz_mm")
        if not isinstance(tip_support, list) or len(tip_support) < 2:
            raise DirectSectionSurfaceError(
                "v116_direct_curve_attachment_invalid",
                "closed direct section network lacks authenticated shroud support",
            )
        tip_loop = _closed_loop_from_grids(base_grids, -1)
        support_loop = _support_loop_from_carrier(
            tip_loop,
            stations[-1]["support_profile_rz_mm"],
            tip_support,
        )
        tip_rows = _transform_grid(
            list(reversed(_attachment_rows(support_loop, tip_loop, row_count=17))),
            transform,
        )
        _replace_attachment_surface(
            closed_tip,
            tip_rows,
            construction="direct_active_tip_to_authenticated_shroud_support",
            boundary_names=("blade_tip_loop", "shroud_attachment_loop"),
        )
        closed_tip["v1_1_tip_quality"] = _direct_tip_quality(
            tip_rows,
            construction="direct_active_tip_to_authenticated_shroud_support",
        )
        replaced.append(str(closed_tip["id"]))
    return replaced


def _replace_exact_root_patch_surfaces(
    surface_inventory: list[dict[str, Any]],
    root_surface: dict[str, Any],
    authorities: Sequence[Mapping[str, Any]],
    transform: np.ndarray,
    *,
    sampled_patches: Sequence[_ExactPatchTemplate] | None = None,
) -> list[str]:
    return _replace_exact_trimmed_patch_surfaces(
        surface_inventory,
        root_surface,
        authorities,
        transform,
        construction="authenticated_source_root_patch",
        quality_key="v1_1_root_quality",
        sampled_patches=sampled_patches,
    )


def _replace_exact_tip_patch_surfaces(
    surface_inventory: list[dict[str, Any]],
    tip_surface: dict[str, Any],
    authorities: Sequence[Mapping[str, Any]],
    transform: np.ndarray,
    *,
    sampled_patches: Sequence[_ExactPatchTemplate] | None = None,
) -> list[str]:
    return _replace_exact_trimmed_patch_surfaces(
        surface_inventory,
        tip_surface,
        authorities,
        transform,
        construction="authenticated_source_open_tip_patch",
        quality_key="v1_1_tip_quality",
        sampled_patches=sampled_patches,
    )


def _replace_exact_trimmed_patch_surfaces(
    surface_inventory: list[dict[str, Any]],
    surface: dict[str, Any],
    authorities: Sequence[Mapping[str, Any]],
    transform: np.ndarray,
    *,
    construction: str,
    quality_key: str,
    sampled_patches: Sequence[_ExactPatchTemplate] | None = None,
) -> list[str]:
    template = _exact_patch_surface_metadata_template(surface)
    base_id = str(surface["id"])
    base_family = str(surface.get("face_family", surface.get("role", "patch")))
    surface.clear()
    surface.update(copy.deepcopy(template))
    if sampled_patches is None:
        sampled_patches = _sample_exact_patch_templates(authorities)
    replaced = []
    for patch_index, (
        authority_index,
        trim_subpatch_index,
        authority,
        sampled,
        sampling,
        source_boundary_templates,
    ) in enumerate(sampled_patches):
        transformed = _transform_grid(sampled, transform)
        target = surface if patch_index == 0 else copy.deepcopy(template)
        if patch_index:
            target["id"] = f"{base_id}_source_patch_{patch_index:02d}"
            surface_inventory.append(target)
        target["face_family"] = f"{base_family}_source_patch_{patch_index:02d}"
        sampled_quality = sampling.get("surface_quality")
        quality = (
            copy.deepcopy(dict(sampled_quality))
            if isinstance(sampled_quality, Mapping)
            and sampled_quality.get("status") == "PASS"
            else _authenticated_trim_surface_quality(transformed)
        )
        quality["rigid_transform_invariant_reuse"] = bool(
            isinstance(sampled_quality, Mapping)
            and sampled_quality.get("status") == "PASS"
        )
        if quality["status"] != "PASS":
            raise DirectSectionSurfaceError(
                "v116_direct_curve_attachment_quality_failed",
                "authenticated source trimmed patch produced an invalid grid",
                {
                    **quality,
                    "source_face_id": str(authority.get("source_face_id", "")),
                    "sampling": sampling,
                },
            )
        target["uv_grid"] = transformed
        target["edge_samples"] = {
            "u_start": copy.deepcopy(transformed[0]),
            "u_end": copy.deepcopy(transformed[-1]),
            "v_start": [copy.deepcopy(row[0]) for row in transformed],
            "v_end": [copy.deepcopy(row[-1]) for row in transformed],
        }
        target["edge_authority"] = _transformed_edge_authority(sampling)
        if trim_subpatch_index == 0:
            target["source_boundary_samples"] = _transform_source_boundary_samples(
                source_boundary_templates,
                transform,
            )
        target["source"] = {
            "authority": "authenticated_step_trimmed_rational_bspline_surface",
            "implementation_revision": IMPLEMENTATION_REVISION,
            "construction": construction,
            "source_face_id": str(authority.get("source_face_id", "")),
            "source_patch_index": patch_index,
            "source_authority_index": authority_index,
            "trim_subpatch_index": trim_subpatch_index,
            "base_face_family": base_family,
            "sampling": sampling,
            "surface_quality": quality,
        }
        target["fidelity"] = (
            "sampled_review_grade_authenticated_trimmed_nurbs_surface"
        )
        target["material"] = True
        target["export_default"] = "included"
        target.setdefault("display", {})["visible_by_default"] = True
        attachment_quality = {
            **quality,
            "construction": construction,
            "geometry_authority": (
                "authenticated_step_trimmed_rational_bspline_surface"
            ),
            "source_face_id": str(authority.get("source_face_id", "")),
        }
        if quality_key == "v1_1_root_quality":
            attachment_quality["material_side_status"] = "PASS"
        elif quality_key == "v1_1_tip_quality":
            attachment_quality["tip_area_ratio"] = 1.0
        elif quality_key == "v1_1_side_quality":
            attachment_quality["trim_domain_status"] = "PASS"
        else:
            attachment_quality["closure_surface_status"] = "PASS"
        target[quality_key] = attachment_quality
        replaced.append(str(target["id"]))
    return replaced


def _exact_patch_surface_metadata_template(
    surface: Mapping[str, Any],
) -> dict[str, Any]:
    geometry_keys = {
        "uv_grid",
        "edge_samples",
        "edge_authority",
        "source_boundary_samples",
        "source",
    }
    return {
        key: copy.deepcopy(value)
        for key, value in surface.items()
        if key not in geometry_keys and not str(key).endswith("_quality")
    }


def _population_exact_patch_templates(
    stations: Sequence[Mapping[str, Any]],
    active_span_authority: Mapping[str, Any],
) -> dict[str, list[_ExactPatchTemplate]]:
    authorities: dict[str, Sequence[Mapping[str, Any]]] = {}
    for role in ("side_a", "side_b"):
        source = _common_source_surface_authority(stations, role)
        if isinstance(source, Mapping) and source.get("trim_boundary_uv_paths"):
            authorities[role] = [source]
    for role, key in (
        ("leading_edge", "leading_edge_surface_patches"),
        ("trailing_edge", "trailing_edge_surface_patches"),
        ("root", "root_surface_patches"),
        ("tip", "tip_surface_patches"),
    ):
        values = active_span_authority.get(key)
        if isinstance(values, list) and values:
            authorities[role] = values
    return {
        role: _sample_exact_patch_templates(values)
        for role, values in authorities.items()
    }


def _sample_exact_patch_templates(
    authorities: Sequence[Mapping[str, Any]],
) -> list[_ExactPatchTemplate]:
    sampled_patches = []
    for authority_index, authority in enumerate(authorities):
        source_boundary_templates = _source_boundary_samples(
            authority,
            np.eye(4, dtype=float),
        )
        for trim_subpatch_index, (sampled, sampling) in enumerate(
            _sample_authenticated_trimmed_surface_patches(authority)
        ):
            sampled_patches.append(
                (
                    authority_index,
                    trim_subpatch_index,
                    authority,
                    sampled,
                    sampling,
                    source_boundary_templates,
                )
            )
    return sampled_patches


def _transformed_edge_authority(
    sampling: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    explicit = sampling.get("edge_authority")
    if isinstance(explicit, Mapping):
        return copy.deepcopy(dict(explicit))
    return {
        role: {"boundary_kind": "source_trim"}
        for role in ("u_start", "u_end", "v_start", "v_end")
    }


def _source_boundary_samples(
    authority: Mapping[str, Any], transform: np.ndarray
) -> list[dict[str, Any]]:
    records = authority.get("trim_boundary_uv_paths")
    if not isinstance(records, Sequence):
        return []
    polygon = None
    interior_center = None
    try:
        paths, _records = _ordered_trim_paths_with_records(
            authority, _trim_boundary_paths(authority)
        )
        polygon = np.vstack([path[:-1] for path in paths])
        interior_center = _trim_polygon_interior_witness(polygon)
    except DirectSectionSurfaceError:
        pass
    result = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            continue
        if record.get("topology_boundary_kind") in _FACE_LOCAL_TRIM_SEAM_KINDS:
            continue
        uv = np.asarray(record.get("uv"), dtype=float)
        if uv.ndim != 2 or uv.shape[0] < 2 or uv.shape[1] != 2:
            continue
        canonical_edge = np.asarray(
            record.get("canonical_points_xyz_mm"), dtype=float
        )
        if (
            canonical_edge.ndim == 2
            and canonical_edge.shape == (len(uv), 3)
            and np.all(np.isfinite(canonical_edge))
        ):
            sampled_uv = uv
            sampled = canonical_edge
        else:
            sample_count = max(17, min(65, 2 * len(uv) - 1))
            sampled_uv = _resample_polyline(uv, sample_count)
            sampled = _evaluate_source_face_surface(
                authority, sampled_uv[None, :, :]
            )[0]
        transformed = _transform_grid([sampled.tolist()], transform)[0]
        differentials = None
        if polygon is not None and interior_center is not None:
            differentials = _source_boundary_differential_samples(
                authority,
                sampled_uv,
                polygon=polygon,
                interior_center=interior_center,
            )
        transformed_normals = []
        curvature_samples = []
        if differentials is not None:
            normals, curvature = differentials
            rotation = np.asarray(transform, dtype=float)[:3, :3]
            transformed_normals = (rotation @ normals.T).T.tolist()
            curvature_samples = curvature.tolist()
        result.append(
            {
                "source_edge_id": str(
                    record.get("source_edge_id") or ""
                ),
                "boundary_path_id": str(
                    record.get("boundary_path_id") or f"trim_path_{index:03d}"
                ),
                "projection_residual_max_mm": float(
                    record.get("projection_residual_max_mm", 0.0)
                ),
                "topology_boundary_kind": str(
                    record.get("topology_boundary_kind")
                    or "material_shared_edge"
                ),
                "samples_xyz_mm": transformed,
                **(
                    {
                        "surface_normal_samples": transformed_normals,
                        "transverse_normal_curvature_samples_per_mm": (
                            curvature_samples
                        ),
                        "differential_measurement_authority": (
                            "source_nurbs_trim_interior_finite_difference"
                        ),
                    }
                    if transformed_normals
                    else {}
                ),
            }
        )
    return result


def _transform_source_boundary_samples(
    templates: Sequence[Mapping[str, Any]], transform: np.ndarray
) -> list[dict[str, Any]]:
    rotation = np.asarray(transform, dtype=float)[:3, :3]
    result = []
    for template in templates:
        record = copy.deepcopy(dict(template))
        points = np.asarray(template.get("samples_xyz_mm"), dtype=float)
        if points.ndim == 2 and points.shape[1] == 3:
            record["samples_xyz_mm"] = _transform_grid(
                [points.tolist()], transform
            )[0]
        normals = np.asarray(template.get("surface_normal_samples"), dtype=float)
        if normals.ndim == 2 and normals.shape[1] == 3:
            record["surface_normal_samples"] = (rotation @ normals.T).T.tolist()
        result.append(record)
    return result


def _source_boundary_differential_samples(
    authority: Mapping[str, Any],
    boundary_uv: np.ndarray,
    *,
    polygon: np.ndarray,
    interior_center: np.ndarray,
) -> tuple[np.ndarray, np.ndarray] | None:
    domain_scale = max(float(np.ptp(polygon, axis=0).max()), 1.0e-9)
    base_step = max(1.0e-8, 2.0e-4 * domain_scale)
    uv = np.asarray(boundary_uv, dtype=float)
    tangent_uv = np.gradient(uv, axis=0)
    first_interior = []
    second_interior = []
    for point, tangent in zip(uv, tangent_uv, strict=True):
        tangent_length = float(np.linalg.norm(tangent))
        if tangent_length <= 1.0e-18:
            return None
        perpendicular = np.asarray([-tangent[1], tangent[0]], dtype=float)
        perpendicular /= max(float(np.linalg.norm(perpendicular)), 1.0e-18)
        selected = None
        step = base_step
        for _attempt in range(10):
            for direction in (perpendicular, -perpendicular):
                first = point + step * direction
                second = point + 2.0 * step * direction
                if _point_inside_trim_polygon(
                    first, polygon
                ) and _point_inside_trim_polygon(second, polygon):
                    selected = (first, second)
                    break
            if selected is not None:
                break
            step *= 0.5
        if selected is None:
            direction = interior_center - point
            direction_length = float(np.linalg.norm(direction))
            if direction_length <= 1.0e-18:
                return None
            direction /= direction_length
            first = point + base_step * direction
            second = point + 2.0 * base_step * direction
            if not _point_inside_trim_polygon(
                first, polygon
            ) or not _point_inside_trim_polygon(second, polygon):
                return None
            selected = (first, second)
        first_interior.append(selected[0])
        second_interior.append(selected[1])
    boundary_xyz = _evaluate_source_face_surface(authority, uv[None, :, :])[0]
    first_xyz = _evaluate_source_face_surface(
        authority, np.asarray(first_interior, dtype=float)[None, :, :]
    )[0]
    second_xyz = _evaluate_source_face_surface(
        authority, np.asarray(second_interior, dtype=float)[None, :, :]
    )[0]
    tangent_xyz = np.gradient(boundary_xyz, axis=0)
    inward_xyz = first_xyz - boundary_xyz
    normals = np.cross(tangent_xyz, inward_xyz)
    normal_lengths = np.linalg.norm(normals, axis=1)
    inward_lengths = np.linalg.norm(inward_xyz, axis=1)
    if (
        np.any(normal_lengths <= 1.0e-15)
        or np.any(inward_lengths <= 1.0e-15)
        or np.any(~np.isfinite(normals))
    ):
        return None
    normals /= normal_lengths[:, None]
    second_difference = second_xyz - 2.0 * first_xyz + boundary_xyz
    curvature = np.abs(np.sum(second_difference * normals, axis=1)) / np.maximum(
        inward_lengths * inward_lengths,
        1.0e-18,
    )
    if np.any(~np.isfinite(curvature)):
        return None
    return normals, curvature


def _trim_polygon_interior_witness(polygon: np.ndarray) -> np.ndarray:
    points = np.asarray(polygon, dtype=float)
    candidates = [
        np.mean(points, axis=0),
        0.5 * (np.min(points, axis=0) + np.max(points, axis=0)),
    ]
    signed_cross = (
        points[:, 0] * np.roll(points[:, 1], -1)
        - np.roll(points[:, 0], -1) * points[:, 1]
    )
    area_factor = float(np.sum(signed_cross))
    if abs(area_factor) > 1.0e-18:
        candidates.insert(
            0,
            np.asarray(
                [
                    np.sum(
                        (points[:, 0] + np.roll(points[:, 0], -1))
                        * signed_cross
                    ),
                    np.sum(
                        (points[:, 1] + np.roll(points[:, 1], -1))
                        * signed_cross
                    ),
                ],
                dtype=float,
            )
            / (3.0 * area_factor),
        )
    for candidate in candidates:
        if _point_inside_trim_polygon(candidate, points):
            return candidate
    minimum = np.min(points, axis=0)
    maximum = np.max(points, axis=0)
    interior = []
    for u in np.linspace(minimum[0], maximum[0], 9)[1:-1]:
        for v in np.linspace(minimum[1], maximum[1], 9)[1:-1]:
            candidate = np.asarray([u, v], dtype=float)
            if _point_inside_trim_polygon(candidate, points):
                interior.append(candidate)
    if not interior:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source trim polygon has no interior differential witness",
        )
    return max(
        interior,
        key=lambda candidate: _point_to_polyline_distance(candidate, points),
    )


def _sample_authenticated_trimmed_surface_patch(
    authority: Mapping[str, Any],
    *,
    stream_sample_count: int = 65,
    span_sample_count: int = 33,
) -> tuple[list[list[list[float]]], dict[str, Any]]:
    paths = _trim_boundary_paths(authority)
    candidates = []
    failures = []
    for stream_axis in (0, 1):
        span_axis = 1 - stream_axis
        path_stream = np.concatenate([path[:, stream_axis] for path in paths])
        stream_start = float(np.min(path_stream))
        stream_end = float(np.max(path_stream))
        stream_values = _source_trim_stream_values(
            authority,
            stream_axis=stream_axis,
            stream_start=stream_start,
            stream_end=stream_end,
            minimum_sample_count=stream_sample_count,
        )
        lower = []
        upper = []
        valid = True
        for stream_index, stream_value in enumerate(stream_values):
            intersections = _trim_span_intersections(
                paths,
                stream_axis=stream_axis,
                span_axis=span_axis,
                stream_value=float(stream_value),
            )
            endpoint_slice = stream_index in {0, len(stream_values) - 1}
            if len(intersections) < 2 or (
                len(intersections) != 2 and not endpoint_slice
            ):
                failures.append(
                    {
                        "stream_axis": "u" if stream_axis == 0 else "v",
                        "reason": "non_monotone_or_unbounded_trim_intersection",
                        "stream_value": float(stream_value),
                        "intersection_count": len(intersections),
                    }
                )
                valid = False
                break
            lower.append(float(min(intersections)))
            upper.append(float(max(intersections)))
        if not valid:
            continue
        lower_values = np.asarray(lower, dtype=float)
        upper_values = np.asarray(upper, dtype=float)
        if np.any(upper_values - lower_values <= 1.0e-10):
            failures.append(
                {
                    "stream_axis": "u" if stream_axis == 0 else "v",
                    "reason": "collapsed_trim_span",
                }
            )
            continue
        span_values = np.linspace(0.0, 1.0, span_sample_count)[:, None]
        sampled_span = (
            lower_values[None, :]
            + span_values * (upper_values - lower_values)[None, :]
        )
        uv_grid = np.empty(
            (span_sample_count, len(stream_values), 2), dtype=float
        )
        uv_grid[:, :, stream_axis] = stream_values[None, :]
        uv_grid[:, :, span_axis] = sampled_span
        sampled = _evaluate_source_face_surface(authority, uv_grid)
        quality = _authenticated_trim_surface_quality(
            sampled, parameter_grid=uv_grid
        )
        candidates.append(
            (
                quality["status"] != "PASS",
                quality["foldover_count"],
                -quality["minimum_grid_edge_mm"],
                sampled,
                {
                    "method": "authenticated_monotone_trim_scanline_grid",
                    "stream_axis": "u" if stream_axis == 0 else "v",
                    "trim_boundary_path_count": len(paths),
                    "stream_sample_count": len(stream_values),
                    "span_sample_count": span_sample_count,
                    "surface_quality": quality,
                    "source_boundary_edge_ids": sorted(
                        {
                            edge_id
                            for index, record in enumerate(
                                authority.get("trim_boundary_uv_paths", ())
                            )
                            if isinstance(record, Mapping)
                            for edge_id in _record_source_edge_ids(record, index)
                        }
                    ),
                },
            )
        )
    passing = [candidate for candidate in candidates if not candidate[0]]
    if not passing:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_quality_failed",
            "authenticated source root patch has no regular trim parameterization",
            {
                "source_face_id": str(authority.get("source_face_id", "")),
                "candidate_quality": [candidate[-1] for candidate in candidates],
                "sampling_failures": failures,
            },
        )
    selected = min(passing, key=lambda candidate: candidate[:3])
    return selected[3].tolist(), selected[4]


def _sample_authenticated_trimmed_surface_patches(
    authority: Mapping[str, Any],
    *,
    stream_sample_count: int = 65,
    span_sample_count: int = 33,
) -> list[tuple[list[list[list[float]]], dict[str, Any]]]:
    records = authority.get("trim_boundary_uv_paths")
    paths = _trim_boundary_paths(authority)
    has_source_edge_identity = bool(
        isinstance(records, Sequence)
        and any(
            isinstance(record, Mapping) and record.get("source_edge_id")
            for record in records
        )
    )
    try:
        sampled, evidence = _sample_authenticated_trimmed_surface_patch(
            authority,
            stream_sample_count=stream_sample_count,
            span_sample_count=span_sample_count,
        )
        return [(sampled, evidence)]
    except DirectSectionSurfaceError:
        if len(paths) == 4 and not has_source_edge_identity:
            raise
    if len(paths) == 3:
        try:
            return _sample_triangular_trimmed_surface_patches(
                authority,
                paths,
                stream_sample_count=stream_sample_count,
                span_sample_count=span_sample_count,
            )
        except DirectSectionSurfaceError:
            ordered, ordered_records = _ordered_trim_paths_with_records(
                authority, paths
            )
            return _sample_trim_polygon_quad_partition(
                authority,
                ordered,
                records=ordered_records,
                row_count=min(max(9, int(span_sample_count)), 17),
                column_count=min(max(17, int(stream_sample_count)), 33),
            )
    try:
        return _sample_boundary_radial_trimmed_surface_patches(
            authority,
            paths,
            stream_sample_count=stream_sample_count,
            span_sample_count=span_sample_count,
        )
    except DirectSectionSurfaceError:
        ordered, ordered_records = _ordered_trim_paths_with_records(
            authority, paths
        )
        return _sample_trim_polygon_quad_partition(
            authority,
            ordered,
            records=ordered_records,
            row_count=min(max(9, int(span_sample_count)), 17),
            column_count=min(max(17, int(stream_sample_count)), 33),
        )


def _sample_boundary_radial_trimmed_surface_patches(
    authority: Mapping[str, Any],
    paths: Sequence[np.ndarray],
    *,
    stream_sample_count: int,
    span_sample_count: int,
) -> list[tuple[list[list[list[float]]], dict[str, Any]]]:
    ordered, ordered_records = _ordered_trim_paths_with_records(authority, paths)
    ordered, ordered_records = _merge_tangent_continuous_trim_paths(
        ordered,
        ordered_records,
    )
    column_count = max(17, int(stream_sample_count))
    row_count = max(9, int(span_sample_count))
    interior_center = _trim_interior_center(
        ordered,
        row_count=row_count,
        column_count=column_count,
    )
    uv_grids = _boundary_radial_parameter_grids(
        ordered,
        interior_center,
        row_count=row_count,
        column_count=column_count,
    )
    result = []
    for patch_index, uv_grid in enumerate(uv_grids):
        sampled = _evaluate_source_face_surface(authority, uv_grid)
        quality = _authenticated_trim_surface_quality(
            sampled, parameter_grid=uv_grid
        )
        current = ordered_records[patch_index]
        previous = ordered_records[(patch_index - 1) % len(ordered_records)]
        current_edge_ids = _record_source_edge_ids(current, patch_index)
        previous_edge_ids = _record_source_edge_ids(
            previous,
            (patch_index - 1) % len(ordered_records),
        )
        evidence = {
            "method": "authenticated_boundary_radial_quad_partition",
            "trim_boundary_path_count": len(ordered),
            "trim_subpatch_index": patch_index,
            "stream_sample_count": column_count,
            "span_sample_count": row_count,
            "source_boundary_edge_ids": sorted(
                set(current_edge_ids + previous_edge_ids)
            ),
            "edge_authority": {
                "u_start": _record_edge_authority(current, patch_index),
                "v_start": _record_edge_authority(
                    previous,
                    (patch_index - 1) % len(ordered_records),
                ),
                "u_end": {"boundary_kind": "internal_patch_edge"},
                "v_end": {"boundary_kind": "internal_patch_edge"},
            },
            "surface_quality": quality,
        }
        if quality["status"] != "PASS":
            raise DirectSectionSurfaceError(
                "v116_direct_curve_attachment_quality_failed",
                "authenticated source trim radial partition is invalid",
                {
                    "source_face_id": str(authority.get("source_face_id", "")),
                    **evidence,
                },
            )
        result.append((sampled.tolist(), evidence))
    return result


def _record_source_edge_ids(record: Mapping[str, Any], index: int) -> list[str]:
    if record.get("topology_boundary_kind") in _FACE_LOCAL_TRIM_SEAM_KINDS:
        return []
    values = record.get("source_edge_ids")
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        result = [str(value) for value in values if str(value)]
        if result:
            return result
    return [
        str(
            record.get("source_edge_id")
            or record.get("boundary_path_id")
            or f"trim_path_{index:03d}"
        )
    ]


def _record_edge_authority(
    record: Mapping[str, Any], index: int
) -> dict[str, Any]:
    topology_boundary_kind = record.get("topology_boundary_kind")
    if topology_boundary_kind in _FACE_LOCAL_TRIM_SEAM_KINDS:
        return {
            "boundary_kind": str(topology_boundary_kind),
            "boundary_path_id": str(
                record.get("boundary_path_id") or f"trim_path_{index:03d}"
            ),
        }
    source_edge_ids = _record_source_edge_ids(record, index)
    return {
        "boundary_kind": "source_trim",
        "source_edge_id": "+".join(source_edge_ids),
    }


def _sample_triangular_trimmed_surface_patches(
    authority: Mapping[str, Any],
    paths: Sequence[np.ndarray],
    *,
    stream_sample_count: int,
    span_sample_count: int,
) -> list[tuple[list[list[list[float]]], dict[str, Any]]]:
    ordered, ordered_records = _ordered_trim_paths_with_records(authority, paths)
    column_count = max(17, int(stream_sample_count))
    row_count = max(9, int(span_sample_count))
    try:
        interior_center = _trim_interior_center(
            ordered,
            row_count=row_count,
            column_count=column_count,
        )
    except DirectSectionSurfaceError as exc:
        if exc.reason != "v116_direct_curve_correspondence_invalid":
            raise
        return _sample_trim_polygon_quad_partition(
            authority,
            ordered,
            records=ordered_records,
            row_count=min(row_count, 9),
            column_count=min(column_count, 17),
        )
    result = []
    uv_grids = _triangular_trim_parameter_grids(
        ordered,
        interior_center,
        row_count=row_count,
        column_count=column_count,
    )
    for patch_index, uv_grid in enumerate(uv_grids):
        sampled = _evaluate_source_face_surface(authority, uv_grid)
        quality = _authenticated_trim_surface_quality(
            sampled, parameter_grid=uv_grid
        )
        current = ordered_records[patch_index]
        previous = ordered_records[(patch_index - 1) % len(ordered_records)]
        current_edge_ids = _record_source_edge_ids(current, patch_index)
        previous_edge_ids = _record_source_edge_ids(
            previous,
            (patch_index - 1) % len(ordered_records),
        )
        evidence = {
            "method": "authenticated_triangular_trim_three_quad_partition",
            "trim_boundary_path_count": 3,
            "trim_subpatch_index": patch_index,
            "stream_sample_count": column_count,
            "span_sample_count": row_count,
            "source_boundary_edge_ids": sorted(
                set(current_edge_ids + previous_edge_ids)
            ),
            "edge_authority": {
                "u_start": _record_edge_authority(current, patch_index),
                "v_start": _record_edge_authority(
                    previous,
                    (patch_index - 1) % len(ordered_records),
                ),
                "u_end": {"boundary_kind": "internal_patch_edge"},
                "v_end": {"boundary_kind": "internal_patch_edge"},
            },
            "surface_quality": quality,
        }
        if quality["status"] != "PASS":
            raise DirectSectionSurfaceError(
                "v116_direct_curve_attachment_quality_failed",
                "authenticated triangular source patch partition is invalid",
                {
                    "source_face_id": str(authority.get("source_face_id", "")),
                    **evidence,
                },
            )
        result.append((sampled.tolist(), evidence))
    return result


def _sample_trim_polygon_quad_partition(
    authority: Mapping[str, Any],
    paths: Sequence[np.ndarray],
    *,
    records: Sequence[Mapping[str, Any]] | None = None,
    row_count: int,
    column_count: int,
) -> list[tuple[list[list[list[float]]], dict[str, Any]]]:
    if records is not None and len(records) != len(paths):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "trim polygon paths and source boundary records do not correspond",
            {
                "source_face_id": str(authority.get("source_face_id", "")),
                "trim_path_count": len(paths),
                "trim_record_count": len(records),
            },
        )
    boundary_tolerance_mm = max(
        0.05,
        max(
            (
                float(record.get("projection_residual_tolerance_mm", 0.0))
                for record in authority.get("trim_boundary_uv_paths", ())
                if isinstance(record, Mapping)
            ),
            default=0.0,
        ),
    )
    source_pcurve_chord_error_bound_mm = max(
        (
            float(record.get("source_pcurve_chord_error_bound_mm", 0.0))
            for record in authority.get("trim_boundary_uv_paths", ())
            if isinstance(record, Mapping)
        ),
        default=0.0,
    )
    approximation_tolerance_mm = (
        boundary_tolerance_mm - source_pcurve_chord_error_bound_mm
    )
    if approximation_tolerance_mm <= 0.0:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_quality_failed",
            "authenticated STEP p-curve chord bound exhausts trim tolerance",
            {
                "source_face_id": str(authority.get("source_face_id", "")),
                "source_pcurve_chord_error_bound_mm": (
                    source_pcurve_chord_error_bound_mm
                ),
                "boundary_chord_tolerance_mm": boundary_tolerance_mm,
            },
        )
    sampled_paths = []
    boundary_errors_mm = []
    for path in paths:
        sampled_path, path_error_mm = _trim_path_physical_sample_subset(
            authority,
            path,
            tolerance_mm=approximation_tolerance_mm,
        )
        sampled_paths.append(sampled_path)
        boundary_errors_mm.append(path_error_mm)
    boundary_records = [
        dict(record)
        for record in (
            records
            if records is not None
            else (
                {
                    "boundary_path_id": f"trim_path_{index:03d}",
                    "topology_boundary_kind": "trim_polygon_boundary_segment",
                }
                for index in range(len(sampled_paths))
            )
        )
    ]
    boundary_approximation_error_mm = max(boundary_errors_mm, default=0.0)
    boundary_error_mm = (
        source_pcurve_chord_error_bound_mm + boundary_approximation_error_mm
    )
    if boundary_error_mm > boundary_tolerance_mm:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_quality_failed",
            "authenticated trim polygon boundary approximation exceeds tolerance",
            {
                "source_face_id": str(authority.get("source_face_id", "")),
                "boundary_chord_error_max_mm": boundary_error_mm,
                "boundary_chord_tolerance_mm": boundary_tolerance_mm,
            },
        )
    polygon = np.vstack([path[:-1] for path in sampled_paths])
    polygon = _remove_collinear_polygon_points(polygon)
    triangles = _ear_clip_trim_polygon(polygon)
    cells = _pair_trim_triangles_into_convex_cells(triangles)
    boundary_error = max(
        float(np.max(_points_to_polyline_distances(path, sampled)))
        for path, sampled in zip(paths, sampled_paths, strict=True)
    )
    result = []
    subpatch_index = 0
    for cell in cells:
        parameter_grids = []
        if len(cell) == 4:
            top = np.linspace(cell[0], cell[1], column_count)
            right = np.linspace(cell[1], cell[2], row_count)
            bottom = np.linspace(cell[3], cell[2], column_count)
            left = np.linspace(cell[0], cell[3], row_count)
            parameter_grids.append(
                _coons_parameter_patch(top, bottom, left, right)
            )
        else:
            center = np.mean(cell, axis=0)
            midpoints = 0.5 * (cell + np.roll(cell, -1, axis=0))
            for vertex_index in range(3):
                vertex = cell[vertex_index]
                next_midpoint = midpoints[vertex_index]
                previous_midpoint = midpoints[(vertex_index - 1) % 3]
                top = np.linspace(vertex, next_midpoint, column_count)
                left = np.linspace(vertex, previous_midpoint, row_count)
                bottom = np.linspace(previous_midpoint, center, column_count)
                right = np.linspace(next_midpoint, center, row_count)
                parameter_grids.append(
                    _coons_parameter_patch(top, bottom, left, right)
                )
        for uv_grid in parameter_grids:
            sampled = _evaluate_source_face_surface(authority, uv_grid)
            quality = _authenticated_trim_surface_quality(
                sampled, parameter_grid=uv_grid
            )
            edge_authority = _trim_polygon_parameter_grid_edge_authority(
                uv_grid,
                sampled_paths,
                boundary_records,
            )
            source_boundary_edge_ids = sorted(
                {
                    str(edge.get("source_edge_id"))
                    for edge in edge_authority.values()
                    if edge.get("boundary_kind") == "source_trim"
                    and edge.get("source_edge_id")
                }
            )
            evidence = {
                "method": "authenticated_trim_polygon_ear_clip_quad_partition",
                "trim_boundary_path_count": len(paths),
                "trim_subpatch_index": subpatch_index,
                "trim_polygon_vertex_count": len(polygon),
                "trim_triangle_count": len(triangles),
                "trim_cell_count": len(cells),
                "trim_cell_vertex_count": len(cell),
                "boundary_parameter_chord_error_max": boundary_error,
                "boundary_chord_error_max_mm": boundary_error_mm,
                "boundary_chord_tolerance_mm": boundary_tolerance_mm,
                "source_pcurve_chord_error_bound_mm": (
                    source_pcurve_chord_error_bound_mm
                ),
                "trim_partition_approximation_error_max_mm": (
                    boundary_approximation_error_mm
                ),
                "stream_sample_count": column_count,
                "span_sample_count": row_count,
                "source_boundary_edge_ids": source_boundary_edge_ids,
                "edge_authority": edge_authority,
                "surface_quality": quality,
            }
            if quality["status"] != "PASS":
                raise DirectSectionSurfaceError(
                    "v116_direct_curve_attachment_quality_failed",
                    "authenticated trim polygon quadrangulation is invalid",
                    {
                        "source_face_id": str(
                            authority.get("source_face_id", "")
                        ),
                        **evidence,
                    },
                )
            result.append((sampled.tolist(), evidence))
            subpatch_index += 1
    return result


def _trim_polygon_parameter_grid_edge_authority(
    uv_grid: np.ndarray,
    boundary_paths: Sequence[np.ndarray],
    boundary_records: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    grid = np.asarray(uv_grid, dtype=float)
    edges = {
        "u_start": (grid[0, 0], grid[0, -1]),
        "u_end": (grid[-1, 0], grid[-1, -1]),
        "v_start": (grid[0, 0], grid[-1, 0]),
        "v_end": (grid[0, -1], grid[-1, -1]),
    }
    scale = max(
        float(np.ptp(np.vstack(boundary_paths), axis=0).max()),
        1.0,
    )
    tolerance = max(1.0e-10, 1.0e-8 * scale)
    return {
        role: _trim_polygon_edge_source_authority(
            start,
            end,
            boundary_paths,
            boundary_records,
            tolerance=tolerance,
        )
        for role, (start, end) in edges.items()
    }


def _trim_polygon_edge_source_authority(
    start: np.ndarray,
    end: np.ndarray,
    boundary_paths: Sequence[np.ndarray],
    boundary_records: Sequence[Mapping[str, Any]],
    *,
    tolerance: float,
) -> dict[str, Any]:
    probes = np.linspace(
        np.asarray(start, dtype=float),
        np.asarray(end, dtype=float),
        9,
    )
    for index, (path, record) in enumerate(
        zip(boundary_paths, boundary_records, strict=True)
    ):
        distances = _points_to_polyline_distances(
            probes,
            np.asarray(path, dtype=float),
        )
        if float(np.max(distances)) > tolerance:
            continue
        topology_kind = record.get("topology_boundary_kind")
        if topology_kind == "trim_polygon_boundary_segment":
            return {
                "boundary_kind": "trim_polygon_boundary_segment",
                "boundary_path_id": str(
                    record.get("boundary_path_id") or f"trim_path_{index:03d}"
                ),
            }
        return _record_edge_authority(record, index)
    return {"boundary_kind": "internal_patch_edge"}


def _pair_trim_triangles_into_convex_cells(
    triangles: Sequence[np.ndarray],
) -> list[np.ndarray]:
    pending = [np.asarray(triangle, dtype=float) for triangle in triangles]
    cells: list[np.ndarray] = []
    tolerance = 1.0e-12 * max(
        max((float(np.ptp(triangle, axis=0).max()) for triangle in pending), default=1.0),
        1.0e-12,
    ) ** 2
    pair_cells: dict[tuple[int, int], np.ndarray] = {}
    adjacency = {index: set() for index in range(len(pending))}
    for first_index, first in enumerate(pending):
        for second_index in range(first_index + 1, len(pending)):
            quad = _convex_union_of_adjacent_triangles(
                first, pending[second_index], tolerance=tolerance
            )
            if quad is None:
                continue
            pair_cells[(first_index, second_index)] = quad
            adjacency[first_index].add(second_index)
            adjacency[second_index].add(first_index)
    remaining = set(range(len(pending)))
    while remaining:
        leaves = sorted(
            index
            for index in remaining
            if len(adjacency[index].intersection(remaining)) <= 1
        )
        current = leaves[0] if leaves else min(remaining)
        neighbors = sorted(adjacency[current].intersection(remaining))
        if not neighbors:
            cells.append(pending[current])
            remaining.remove(current)
            continue
        neighbor = neighbors[0]
        pair_key = (min(current, neighbor), max(current, neighbor))
        cells.append(pair_cells[pair_key])
        remaining.remove(current)
        remaining.remove(neighbor)
    return cells


def _convex_union_of_adjacent_triangles(
    first: np.ndarray,
    second: np.ndarray,
    *,
    tolerance: float,
) -> np.ndarray | None:
    unique: list[np.ndarray] = []
    shared_count = 0
    for point in np.vstack((first, second)):
        match = next(
            (
                existing
                for existing in unique
                if float(np.linalg.norm(existing - point)) <= math.sqrt(tolerance)
            ),
            None,
        )
        if match is None:
            unique.append(point.copy())
        else:
            shared_count += 1
    if len(unique) != 4 or shared_count != 2:
        return None
    points = np.asarray(unique, dtype=float)
    center = np.mean(points, axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    ordered = points[np.argsort(angles)]
    crosses = np.asarray(
        [
            _cross_2d(
                ordered[(index + 1) % 4] - ordered[index],
                ordered[(index + 2) % 4] - ordered[(index + 1) % 4],
            )
            for index in range(4)
        ],
        dtype=float,
    )
    if np.any(crosses <= tolerance):
        return None
    triangle_area = sum(abs(_polygon_signed_area(triangle)) for triangle in (first, second))
    quad_area = abs(_polygon_signed_area(ordered))
    if abs(quad_area - triangle_area) > max(tolerance, 1.0e-9 * triangle_area):
        return None
    return ordered


def _polygon_signed_area(polygon: np.ndarray) -> float:
    points = np.asarray(polygon, dtype=float)
    return 0.5 * float(
        np.sum(
            points[:, 0] * np.roll(points[:, 1], -1)
            - np.roll(points[:, 0], -1) * points[:, 1]
        )
    )


def _trim_boundary_chord_error_mm(
    authority: Mapping[str, Any],
    source_paths: Sequence[np.ndarray],
    sampled_paths: Sequence[np.ndarray],
) -> float:
    maximum = 0.0
    for source_path, sampled_path in zip(
        source_paths, sampled_paths, strict=True
    ):
        source_xyz = _evaluate_source_face_surface(
            authority, np.asarray(source_path, dtype=float)[None, :, :]
        )[0]
        sampled_xyz = _evaluate_source_face_surface(
            authority, np.asarray(sampled_path, dtype=float)[None, :, :]
        )[0]
        maximum = max(
            maximum,
            float(np.max(_points_to_polyline_distances(source_xyz, sampled_xyz))),
        )
    return maximum


def _trim_path_physical_sample_subset(
    authority: Mapping[str, Any],
    path: np.ndarray,
    *,
    tolerance_mm: float,
) -> tuple[np.ndarray, float]:
    parameters = np.asarray(path, dtype=float)
    if len(parameters) <= 2:
        return parameters.copy(), 0.0
    source_xyz = _evaluate_source_face_surface(
        authority, parameters[None, :, :]
    )[0]
    retained = {0, len(parameters) - 1}
    pending = [(0, len(parameters) - 1)]
    while pending:
        first, last = pending.pop()
        if last <= first + 1:
            continue
        sample_indices = np.arange(first + 1, last)
        fractions = ((sample_indices - first) / (last - first))[:, None]
        linear_parameters = (
            (1.0 - fractions) * parameters[first]
            + fractions * parameters[last]
        )
        linear_xyz = _evaluate_source_face_surface(
            authority, linear_parameters[None, :, :]
        )[0]
        distances = np.linalg.norm(
            source_xyz[sample_indices] - linear_xyz, axis=1
        )
        maximum_offset = int(np.argmax(distances))
        if float(distances[maximum_offset]) > tolerance_mm:
            split = int(sample_indices[maximum_offset])
            retained.add(split)
            pending.extend(((first, split), (split, last)))
    indexes = sorted(retained)
    maximum = 0.0
    for first, last in zip(indexes[:-1], indexes[1:], strict=True):
        sample_indices = np.arange(first, last + 1)
        fractions = ((sample_indices - first) / (last - first))[:, None]
        linear_parameters = (
            (1.0 - fractions) * parameters[first]
            + fractions * parameters[last]
        )
        linear_xyz = _evaluate_source_face_surface(
            authority, linear_parameters[None, :, :]
        )[0]
        maximum = max(
            maximum,
            float(
                np.max(
                    np.linalg.norm(
                        source_xyz[sample_indices] - linear_xyz,
                        axis=1,
                    )
                )
            ),
        )
    return parameters[indexes].copy(), maximum


def _trim_path_sample_subset(
    path: np.ndarray, maximum_sample_count: int
) -> np.ndarray:
    points = np.asarray(path, dtype=float)
    if len(points) <= maximum_sample_count:
        return points.copy()
    indexes = np.unique(
        np.rint(
            np.linspace(0, len(points) - 1, maximum_sample_count)
        ).astype(int)
    )
    return points[indexes].copy()


def _remove_collinear_polygon_points(polygon: np.ndarray) -> np.ndarray:
    points = [np.asarray(point, dtype=float) for point in polygon]
    scale = max(float(np.ptp(polygon, axis=0).max()), 1.0e-6)
    tolerance = 1.0e-10 * scale * scale
    changed = True
    while changed and len(points) > 3:
        changed = False
        retained = []
        for index, point in enumerate(points):
            previous = points[(index - 1) % len(points)]
            following = points[(index + 1) % len(points)]
            cross = abs(_cross_2d(point - previous, following - point))
            if cross <= tolerance:
                changed = True
            else:
                retained.append(point)
        if len(retained) < 3:
            break
        points = retained
    return np.asarray(points, dtype=float)


def _ear_clip_trim_polygon(polygon: np.ndarray) -> list[np.ndarray]:
    area = 0.5 * float(
        np.sum(
            polygon[:, 0] * np.roll(polygon[:, 1], -1)
            - np.roll(polygon[:, 0], -1) * polygon[:, 1]
        )
    )
    points = polygon if area > 0.0 else polygon[::-1].copy()
    indices = list(range(len(points)))
    triangles = []
    tolerance = 1.0e-12 * max(float(np.ptp(points, axis=0).max()) ** 2, 1.0e-12)
    while len(indices) > 3:
        clipped = False
        for offset, current_index in enumerate(indices):
            previous_index = indices[(offset - 1) % len(indices)]
            next_index = indices[(offset + 1) % len(indices)]
            triangle = points[[previous_index, current_index, next_index]]
            cross = _cross_2d(
                triangle[1] - triangle[0], triangle[2] - triangle[1]
            )
            if cross <= tolerance:
                continue
            if any(
                _point_inside_triangle(points[index], triangle, tolerance)
                for index in indices
                if index not in {previous_index, current_index, next_index}
            ):
                continue
            triangles.append(triangle)
            del indices[offset]
            clipped = True
            break
        if not clipped:
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                "source NURBS trim polygon cannot be quadrangulated",
                {"trim_polygon_vertex_count": len(points)},
            )
    triangles.append(points[indices])
    return triangles


def _point_inside_triangle(
    point: np.ndarray, triangle: np.ndarray, tolerance: float
) -> bool:
    signs = []
    for index in range(3):
        start = triangle[index]
        end = triangle[(index + 1) % 3]
        signs.append(_cross_2d(end - start, point - start))
    return all(value >= -tolerance for value in signs)


def _cross_2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(first[0] * second[1] - first[1] * second[0])


def _ordered_closed_trim_paths(paths: Sequence[np.ndarray]) -> list[np.ndarray]:
    remaining = [np.asarray(path, dtype=float).copy() for path in paths]
    ordered = [remaining.pop(0)]
    scale = max(
        float(np.ptp(np.concatenate(paths, axis=0), axis=0).max()),
        1.0e-6,
    )
    tolerance = max(1.0e-8, 5.0e-5 * scale)
    while remaining:
        endpoint = ordered[-1][-1]
        candidates = []
        for index, path in enumerate(remaining):
            candidates.append(
                (float(np.linalg.norm(endpoint - path[0])), index, False)
            )
            candidates.append(
                (float(np.linalg.norm(endpoint - path[-1])), index, True)
            )
        distance, index, reverse = min(candidates)
        if distance > tolerance:
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                "source NURBS trim paths do not form a closed loop",
                {"trim_path_join_gap": distance, "tolerance": tolerance},
            )
        selected = remaining.pop(index)
        ordered.append(selected[::-1].copy() if reverse else selected)
    closure_gap = float(np.linalg.norm(ordered[-1][-1] - ordered[0][0]))
    if closure_gap > tolerance:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS trim paths do not close",
            {"trim_path_closure_gap": closure_gap, "tolerance": tolerance},
        )
    return ordered


def _ordered_trim_paths_with_records(
    authority: Mapping[str, Any],
    paths: Sequence[np.ndarray],
) -> tuple[list[np.ndarray], list[dict[str, Any]]]:
    raw_records = authority.get("trim_boundary_uv_paths")
    if not isinstance(raw_records, Sequence) or len(raw_records) != len(paths):
        raw_records = [
            {"boundary_path_id": f"trim_path_{index:03d}"}
            for index in range(len(paths))
        ]
    remaining = [
        (
            np.asarray(path, dtype=float).copy(),
            dict(record),
            _trim_record_endpoint_points(record),
        )
        for path, record in zip(paths, raw_records, strict=True)
    ]
    use_physical_endpoints = all(item[2] is not None for item in remaining)
    first_path, first_record, first_endpoints = remaining.pop(0)
    ordered_paths = [first_path]
    ordered_records = [first_record]
    ordered_endpoints = [first_endpoints]
    scale = max(
        float(np.ptp(np.concatenate(paths, axis=0), axis=0).max()),
        1.0e-6,
    )
    uv_tolerance = max(1.0e-8, 5.0e-5 * scale)
    physical_tolerance = max(
        0.005,
        max(
            (
                float(record.get("projection_residual_tolerance_mm", 0.0))
                for record in raw_records
                if isinstance(record, Mapping)
            ),
            default=0.0,
        ),
        max(
            (
                float(value)
                for record in raw_records
                if isinstance(record, Mapping)
                for value in record.get("source_vertex_tolerances_mm", ())
                if isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
            ),
            default=0.0,
        ),
    )
    tolerance = physical_tolerance if use_physical_endpoints else uv_tolerance
    while remaining:
        endpoint = (
            ordered_endpoints[-1][1]
            if use_physical_endpoints
            else ordered_paths[-1][-1]
        )
        candidates = []
        for index, (path, _record, physical_endpoints) in enumerate(remaining):
            candidate_start = (
                physical_endpoints[0]
                if use_physical_endpoints
                else path[0]
            )
            candidate_end = (
                physical_endpoints[1]
                if use_physical_endpoints
                else path[-1]
            )
            candidates.append(
                (float(np.linalg.norm(endpoint - candidate_start)), index, False)
            )
            candidates.append(
                (float(np.linalg.norm(endpoint - candidate_end)), index, True)
            )
        distance, index, reverse = min(candidates)
        if distance > tolerance:
            raise DirectSectionSurfaceError(
                "v116_direct_curve_correspondence_invalid",
                "source NURBS trim paths do not form a closed loop",
                {
                    "source_face_id": str(authority.get("source_face_id", "")),
                    "trim_path_join_gap": distance,
                    "tolerance": tolerance,
                    "distance_authority": (
                        "canonical_step_edge_endpoint_xyz_mm"
                        if use_physical_endpoints
                        else "face_uv_parameter_distance"
                    ),
                },
            )
        selected, record, physical_endpoints = remaining.pop(index)
        ordered_paths.append(selected[::-1].copy() if reverse else selected)
        ordered_records.append(record)
        ordered_endpoints.append(
            None
            if physical_endpoints is None
            else (
                physical_endpoints[::-1].copy()
                if reverse
                else physical_endpoints
            )
        )
    closing_gap = float(
        np.linalg.norm(
            ordered_endpoints[-1][1] - ordered_endpoints[0][0]
            if use_physical_endpoints
            else ordered_paths[-1][-1] - ordered_paths[0][0]
        )
    )
    if closing_gap > tolerance:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS trim paths do not close",
            {
                "source_face_id": str(authority.get("source_face_id", "")),
                "trim_path_closure_gap": closing_gap,
                "tolerance": tolerance,
                "distance_authority": (
                    "canonical_step_edge_endpoint_xyz_mm"
                    if use_physical_endpoints
                    else "face_uv_parameter_distance"
                ),
            },
        )
    return ordered_paths, ordered_records


def _trim_record_endpoint_points(
    record: Mapping[str, Any],
) -> np.ndarray | None:
    for key in ("canonical_points_xyz_mm", "source_points_xyz_mm"):
        points = np.asarray(record.get(key), dtype=float)
        if (
            points.ndim == 2
            and points.shape[0] >= 2
            and points.shape[1] == 3
            and np.all(np.isfinite(points))
        ):
            return np.asarray([points[0], points[-1]], dtype=float)
    return None


def _merge_tangent_continuous_trim_paths(
    paths: Sequence[np.ndarray],
    records: Sequence[Mapping[str, Any]],
    *,
    tangent_cosine_tolerance: float = 0.9995,
) -> tuple[list[np.ndarray], list[dict[str, Any]]]:
    merged_paths = [np.asarray(path, dtype=float).copy() for path in paths]
    merged_records = []
    for index, record in enumerate(records):
        merged_records.append(
            {
                **dict(record),
                "source_edge_ids": _record_source_edge_ids(record, index),
            }
        )
    changed = True
    while changed and len(merged_paths) > 3:
        changed = False
        for index in range(len(merged_paths)):
            next_index = (index + 1) % len(merged_paths)
            first = merged_paths[index]
            second = merged_paths[next_index]
            first_tangent = first[-1] - first[-2]
            second_tangent = second[1] - second[0]
            denominator = float(
                np.linalg.norm(first_tangent) * np.linalg.norm(second_tangent)
            )
            if denominator <= 1.0e-18:
                continue
            cosine = float(np.dot(first_tangent, second_tangent) / denominator)
            if cosine < tangent_cosine_tolerance:
                continue
            combined_path = np.vstack([first, second[1:]])
            combined_record = {
                "boundary_path_id": (
                    f"{merged_records[index].get('boundary_path_id', index)}+"
                    f"{merged_records[next_index].get('boundary_path_id', next_index)}"
                ),
                "source_edge_ids": [
                    *merged_records[index]["source_edge_ids"],
                    *merged_records[next_index]["source_edge_ids"],
                ],
            }
            if next_index == 0:
                merged_paths = [combined_path, *merged_paths[1:index]]
                merged_records = [combined_record, *merged_records[1:index]]
            else:
                merged_paths[index] = combined_path
                merged_records[index] = combined_record
                del merged_paths[next_index]
                del merged_records[next_index]
            changed = True
            break
    return merged_paths, merged_records


def _trim_interior_center(
    paths: Sequence[np.ndarray],
    *,
    row_count: int = 9,
    column_count: int = 17,
) -> np.ndarray:
    polygon = np.vstack(
        [
            _resample_polyline(path, 65)[:-1]
            for path in paths
        ]
    )
    minimum = np.min(polygon, axis=0)
    maximum = np.max(polygon, axis=0)
    low_resolution_boundaries = _boundary_radial_parameter_boundaries(
        paths,
        row_count=9,
        column_count=17,
    )
    candidates = []
    for u in np.linspace(minimum[0], maximum[0], 31):
        for v in np.linspace(minimum[1], maximum[1], 31):
            point = np.asarray([u, v], dtype=float)
            if _point_inside_trim_polygon(point, polygon):
                parameter_quality = _boundary_radial_parameter_partition_quality(
                    paths,
                    point,
                    boundaries=low_resolution_boundaries,
                )
                if parameter_quality["status"] == "PASS":
                    candidates.append(
                        (
                            parameter_quality["minimum_abs_jacobian"],
                            _point_to_polyline_distance(point, polygon),
                            -u,
                            -v,
                            point,
                        )
                    )
    if not candidates:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS trim has no resolvable interior parameter point",
        )
    if row_count <= 9 and column_count <= 17:
        return max(candidates, key=lambda candidate: candidate[:4])[4]
    high_resolution_boundaries = _boundary_radial_parameter_boundaries(
        paths,
        row_count=row_count,
        column_count=column_count,
    )
    high_resolution_candidates = []
    for candidate in sorted(
        candidates,
        key=lambda value: value[:4],
        reverse=True,
    ):
        quality = _boundary_radial_parameter_partition_quality(
            paths,
            candidate[4],
            boundaries=high_resolution_boundaries,
        )
        if quality["status"] == "PASS":
            high_resolution_candidates.append(
                (
                    quality["minimum_abs_jacobian"],
                    candidate[1],
                    candidate[2],
                    candidate[3],
                    candidate[4],
                )
            )
    if not high_resolution_candidates:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_correspondence_invalid",
            "source NURBS trim has no foldover-free interior parameter point at final resolution",
            {
                "row_count": row_count,
                "column_count": column_count,
            },
        )
    return max(
        high_resolution_candidates,
        key=lambda candidate: candidate[:4],
    )[4]


def _triangular_parameter_partition_quality(
    paths: Sequence[np.ndarray], center: np.ndarray
) -> dict[str, Any]:
    return _boundary_radial_parameter_partition_quality(paths, center)


def _boundary_radial_parameter_partition_quality(
    paths: Sequence[np.ndarray],
    center: np.ndarray,
    *,
    boundaries: Sequence[tuple[np.ndarray, np.ndarray]] | None = None,
) -> dict[str, Any]:
    grids = _boundary_radial_parameter_grids(
        paths,
        center,
        row_count=9,
        column_count=17,
        boundaries=boundaries,
    )
    minimum = math.inf
    for grid in grids:
        row_vectors = np.diff(grid, axis=1)[:-1]
        span_vectors = np.diff(grid, axis=0)[:, :-1]
        jacobian = (
            row_vectors[:, :, 0] * span_vectors[:, :, 1]
            - row_vectors[:, :, 1] * span_vectors[:, :, 0]
        )
        minimum = min(minimum, float(np.min(np.abs(jacobian))))
        nonzero = jacobian[np.abs(jacobian) > 1.0e-14]
        if len(nonzero) != jacobian.size:
            return {"status": "FAIL", "minimum_abs_jacobian": minimum}
        dominant = 1.0 if float(np.median(nonzero)) > 0.0 else -1.0
        if np.any(dominant * nonzero <= 0.0):
            return {"status": "FAIL", "minimum_abs_jacobian": minimum}
    return {"status": "PASS", "minimum_abs_jacobian": minimum}


def _triangular_trim_parameter_grids(
    paths: Sequence[np.ndarray],
    center: np.ndarray,
    *,
    row_count: int,
    column_count: int,
) -> list[np.ndarray]:
    return _boundary_radial_parameter_grids(
        paths,
        center,
        row_count=row_count,
        column_count=column_count,
    )


def _boundary_radial_parameter_grids(
    paths: Sequence[np.ndarray],
    center: np.ndarray,
    *,
    row_count: int,
    column_count: int,
    boundaries: Sequence[tuple[np.ndarray, np.ndarray]] | None = None,
) -> list[np.ndarray]:
    boundary_pairs = list(
        boundaries
        or _boundary_radial_parameter_boundaries(
            paths,
            row_count=row_count,
            column_count=column_count,
        )
    )
    result = []
    for top, left in boundary_pairs:
        bottom = np.linspace(left[-1], center, len(top))
        right = np.linspace(top[-1], center, len(left))
        result.append(_coons_parameter_patch(top, bottom, left, right))
    return result


def _boundary_radial_parameter_boundaries(
    paths: Sequence[np.ndarray],
    *,
    row_count: int,
    column_count: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    result = []
    for patch_index in range(len(paths)):
        current_first, _current_second = _trim_path_half_samples(
            paths[patch_index], column_count
        )
        _previous_first, previous_second = _trim_path_half_samples(
            paths[(patch_index - 1) % len(paths)], row_count
        )
        result.append(
            (
                current_first,
                previous_second[::-1],
            )
        )
    return result


def _trim_path_half_samples(
    path: np.ndarray, maximum_half_sample_count: int
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(path, dtype=float)
    if len(points) >= 5:
        midpoint_index = len(points) // 2
        first = _trim_path_sample_subset(
            points[: midpoint_index + 1], maximum_half_sample_count
        )
        second = _trim_path_sample_subset(
            points[midpoint_index:], maximum_half_sample_count
        )
        return first, second
    sampled = _resample_polyline(
        points, max(3, 2 * int(maximum_half_sample_count) - 1)
    )
    midpoint_index = len(sampled) // 2
    return sampled[: midpoint_index + 1], sampled[midpoint_index:]


def _point_inside_trim_polygon(point: np.ndarray, polygon: np.ndarray) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x0, y0 = previous
        x1, y1 = current
        if (y0 > y) != (y1 > y):
            crossing = (x1 - x0) * (y - y0) / (y1 - y0) + x0
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _point_to_polyline_distance(point: np.ndarray, polygon: np.ndarray) -> float:
    starts = polygon
    ends = np.roll(polygon, -1, axis=0)
    vectors = ends - starts
    length_sq = np.sum(vectors * vectors, axis=1)
    parameters = np.divide(
        np.sum((point - starts) * vectors, axis=1),
        length_sq,
        out=np.zeros_like(length_sq),
        where=length_sq > 1.0e-20,
    )
    projections = starts + np.clip(parameters, 0.0, 1.0)[:, None] * vectors
    return float(np.min(np.linalg.norm(projections - point, axis=1)))


def _coons_parameter_patch(
    top: np.ndarray,
    bottom: np.ndarray,
    left: np.ndarray,
    right: np.ndarray,
) -> np.ndarray:
    top = np.asarray(top, dtype=float)
    bottom = np.asarray(bottom, dtype=float)
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    c00, c01 = top[0], top[-1]
    c10, c11 = bottom[0], bottom[-1]
    u = np.linspace(0.0, 1.0, len(left))[:, None, None]
    v = np.linspace(0.0, 1.0, len(top))[None, :, None]
    row_blend = (1.0 - u) * top[None, :, :] + u * bottom[None, :, :]
    column_blend = (1.0 - v) * left[:, None, :] + v * right[:, None, :]
    corner = (
        (1.0 - u) * (1.0 - v) * c00
        + (1.0 - u) * v * c01
        + u * (1.0 - v) * c10
        + u * v * c11
    )
    return row_blend + column_blend - corner


def _replace_attachment_surface(
    surface: dict[str, Any],
    rows: list[list[list[float]]],
    *,
    construction: str,
    boundary_names: tuple[str, str],
) -> None:
    quality = _single_surface_quality(rows)
    if quality["status"] != "PASS":
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_quality_failed",
            f"{construction} produced an invalid attachment grid",
            quality,
        )
    surface["uv_grid"] = rows
    surface["edge_samples"] = {
        boundary_names[0]: copy.deepcopy(rows[0]),
        boundary_names[1]: copy.deepcopy(rows[-1]),
    }
    surface["source"] = {
        "authority": "authenticated_step_exact_section_curve_network",
        "implementation_revision": IMPLEMENTATION_REVISION,
        "construction": construction,
        "surface_quality": quality,
    }
    surface["fidelity"] = "sampled_review_grade_direct_section_curve_attachment"


def _direct_root_quality(
    rows: Sequence[Sequence[Sequence[float]]],
    *,
    construction: str,
) -> dict[str, Any]:
    quality = _single_surface_quality(rows)
    points = np.asarray(rows, dtype=float)
    separation = np.linalg.norm(points[-1] - points[0], axis=1)
    return {
        **quality,
        "status": "PASS" if quality["status"] == "PASS" else "FAIL",
        "material_side_status": (
            "PASS" if quality["status"] == "PASS" else "FAIL"
        ),
        "construction": construction,
        "geometry_authority": "authenticated_step_direct_section_curve_network",
        "material_side_basis": (
            "ordered_hub_support_to_authenticated_active_root_carrier"
        ),
        "support_to_blade_separation_min_mm": float(np.min(separation)),
        "support_to_blade_separation_max_mm": float(np.max(separation)),
    }


def _direct_tip_quality(
    rows: Sequence[Sequence[Sequence[float]]],
    *,
    construction: str,
) -> dict[str, Any]:
    quality = _single_surface_quality(rows)
    return {
        **quality,
        "status": "PASS" if quality["status"] == "PASS" else "FAIL",
        "construction": construction,
        "geometry_authority": "authenticated_step_direct_section_curve_network",
        "tip_area_ratio": 1.0,
    }


def _attachment_topology_contract(
    surfaces: Sequence[Mapping[str, Any]],
    *,
    tolerance_mm: float,
    require_source_identity: bool = True,
) -> dict[str, Any]:
    tolerance = float(tolerance_mm)
    if not require_source_identity:
        return {
            "contract_id": "impeller_v1_1_6_attachment_topology_r16_24",
            "status": "NOT_APPLICABLE",
            "reason": "strict_source_topology_not_authorized",
            "matched_shared_edge_count": 0,
            "unowned_blade_side_source_boundary_count": 0,
            "max_coordinate_gap_mm": 0.0,
            "orientation_mismatch_count": 0,
            "regular_edge_continuity_status": "NOT_MEASURED",
            "corner_coupling_status": "NOT_MEASURED",
            "continuity_status": "NOT_MEASURED",
            "shared_edges": [],
        }
    records = []
    incomplete_source_identity = []
    surface_by_id = {}
    for surface in surfaces:
        surface_id = str(surface.get("id", ""))
        surface_by_id[surface_id] = surface
        blade_class = surface.get("blade_class")
        blade_index = surface.get("blade_pair_index")
        role = str(surface.get("role", ""))
        if blade_class is None or blade_index is None:
            continue
        source_boundaries = surface.get("source_boundary_samples")
        if isinstance(source_boundaries, Sequence) and source_boundaries:
            for boundary in source_boundaries:
                if not isinstance(boundary, Mapping):
                    continue
                if (
                    boundary.get("topology_boundary_kind")
                    in _FACE_LOCAL_TRIM_SEAM_KINDS
                ):
                    continue
                points = np.asarray(boundary.get("samples_xyz_mm"), dtype=float)
                if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] != 3:
                    continue
                record = {
                        "surface_id": surface_id,
                        "surface_role": role,
                        "blade_class": str(blade_class),
                        "blade_pair_index": int(blade_index),
                        "edge_role": f"source:{boundary.get('boundary_path_id', '')}",
                        "source_edge_id": str(boundary.get("source_edge_id") or ""),
                        "samples": points,
                        "surface_normal_samples": boundary.get(
                            "surface_normal_samples"
                        ),
                        "transverse_normal_curvature_samples_per_mm": boundary.get(
                            "transverse_normal_curvature_samples_per_mm"
                        ),
                    }
                records.append(record)
                if require_source_identity and not record["source_edge_id"]:
                    incomplete_source_identity.append(record)
            continue
        authority = surface.get("edge_authority")
        if not isinstance(authority, Mapping):
            continue
        for edge_role, samples in (surface.get("edge_samples") or {}).items():
            edge_meta = authority.get(edge_role)
            if (
                not isinstance(edge_meta, Mapping)
                or edge_meta.get("boundary_kind") != "source_trim"
            ):
                continue
            points = np.asarray(samples, dtype=float)
            if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] != 3:
                continue
            record = {
                    "surface_id": surface_id,
                    "surface_role": role,
                    "blade_class": str(blade_class),
                    "blade_pair_index": int(blade_index),
                    "edge_role": str(edge_role),
                    "source_edge_id": str(edge_meta.get("source_edge_id") or ""),
                    "samples": points,
                }
            records.append(record)
            if require_source_identity and not record["source_edge_id"]:
                incomplete_source_identity.append(record)
    if require_source_identity and incomplete_source_identity:
        return {
            "contract_id": "impeller_v1_1_6_attachment_topology_r16_24",
            "status": "FAIL",
            "reason": "source_edge_identity_incomplete",
            "source_boundary_record_count": len(records),
            "missing_source_edge_identity_count": len(incomplete_source_identity),
            "missing_source_edge_identity": [
                {
                    key: record[key]
                    for key in (
                        "surface_id",
                        "surface_role",
                        "edge_role",
                        "blade_class",
                        "blade_pair_index",
                    )
                }
                for record in incomplete_source_identity
            ],
            "matched_shared_edge_count": 0,
            "unowned_blade_side_source_boundary_count": 0,
            "max_coordinate_gap_mm": 0.0,
            "orientation_mismatch_count": 0,
            "regular_edge_continuity_status": "NOT_MEASURED",
            "corner_coupling_status": "NOT_MEASURED",
            "continuity_status": "NOT_MEASURED",
            "shared_edges": [],
        }
    identified = [record for record in records if record["source_edge_id"]]
    if require_source_identity and not identified:
        return {
            "contract_id": "impeller_v1_1_6_attachment_topology_r16_24",
            "status": "FAIL",
            "reason": "source_edge_identity_not_available",
            "matched_shared_edge_count": 0,
            "unowned_blade_side_source_boundary_count": 0,
            "max_coordinate_gap_mm": 0.0,
            "orientation_mismatch_count": 0,
            "regular_edge_continuity_status": "NOT_MEASURED",
            "corner_coupling_status": "NOT_MEASURED",
            "continuity_status": "NOT_MEASURED",
            "shared_edges": [],
        }
    candidates = identified if require_source_identity else records
    pair_candidates = []
    candidate_groups: dict[tuple[str, int], list[int]] = {}
    for candidate_index, candidate in enumerate(candidates):
        candidate_groups.setdefault(
            (
                str(candidate["blade_class"]),
                int(candidate["blade_pair_index"]),
            ),
            [],
        ).append(candidate_index)
    geometric_candidate_pair_count = 0
    for group_indices in candidate_groups.values():
        for local_index, first_index in enumerate(group_indices):
            first = candidates[first_index]
            for second_index in group_indices[local_index + 1 :]:
                second = candidates[second_index]
                if first["surface_id"] == second["surface_id"]:
                    continue
                if (
                    first["source_edge_id"]
                    and second["source_edge_id"]
                    and first["source_edge_id"] != second["source_edge_id"]
                ):
                    continue
                geometric_candidate_pair_count += 1
                gap, orientation = _arc_length_boundary_gap(
                    first["samples"], second["samples"]
                )
                if gap <= tolerance:
                    pair_candidates.append(
                        (gap, first_index, second_index, orientation)
                    )
    used = set()
    shared_edges = []
    for gap, first_index, second_index, orientation in sorted(pair_candidates):
        if first_index in used or second_index in used:
            continue
        used.update((first_index, second_index))
        first = candidates[first_index]
        second = candidates[second_index]
        continuity = _matched_edge_continuity(
            first,
            second,
            surface_by_id[first["surface_id"]],
            first["edge_role"],
            surface_by_id[second["surface_id"]],
            second["edge_role"],
            orientation=orientation,
        )
        shared_edges.append(
            {
                "id": f"attachment_shared_edge_{len(shared_edges):04d}",
                "source_edge_id": first["source_edge_id"] or second["source_edge_id"],
                "first_surface_id": first["surface_id"],
                "first_edge_role": first["edge_role"],
                "second_surface_id": second["surface_id"],
                "second_edge_role": second["edge_role"],
                "orientation": orientation,
                "max_gap_mm": gap,
                **continuity,
            }
        )
    unowned = [
        {
            key: record[key]
            for key in (
                "surface_id",
                "surface_role",
                "edge_role",
                "source_edge_id",
                "blade_class",
                "blade_pair_index",
            )
        }
        for index, record in enumerate(candidates)
        if index not in used
        and record["surface_role"] in {"blade_pressure", "blade_suction"}
    ]
    maximum_gap = max(
        (float(edge["max_gap_mm"]) for edge in shared_edges),
        default=0.0,
    )
    measured_edges = [
        edge
        for edge in shared_edges
        if edge.get("differential_measurement_status") == "MEASURED"
    ]
    maximum_normal_angle = max(
        (
            float(edge["normal_angle_interior_max_deg"])
            for edge in measured_edges
        ),
        default=0.0,
    )
    maximum_curvature_mismatch = max(
        (
            float(edge["curvature_proxy_mismatch_interior_max"])
            for edge in measured_edges
        ),
        default=0.0,
    )
    maximum_corner_normal_angle = max(
        (float(edge["normal_angle_endpoint_max_deg"]) for edge in measured_edges),
        default=0.0,
    )
    maximum_corner_curvature_mismatch = max(
        (
            float(edge["curvature_proxy_mismatch_endpoint_max"])
            for edge in measured_edges
        ),
        default=0.0,
    )
    measured_count = len(measured_edges)
    unmeasured_count = len(shared_edges) - measured_count
    g1_status = "NOT_MEASURED"
    g2_status = "NOT_MEASURED"
    if measured_count:
        g1_status = (
            "PASS"
            if maximum_normal_angle <= 5.0
            else "MEASURED_DISCONTINUOUS"
        )
        g2_status = (
            "PASS"
            if maximum_normal_angle <= 5.0
            and maximum_curvature_mismatch <= 0.35
            else "MEASURED_DISCONTINUOUS"
        )
        if unmeasured_count and g1_status == "PASS":
            g1_status = "PARTIAL_PASS"
        if unmeasured_count and g2_status == "PASS":
            g2_status = "PARTIAL_PASS"
    regular_edge_continuity_status = "NOT_MEASURED"
    if "MEASURED_DISCONTINUOUS" in {g1_status, g2_status}:
        regular_edge_continuity_status = "FAIL"
    elif "PARTIAL_PASS" in {g1_status, g2_status}:
        regular_edge_continuity_status = "PARTIAL_PASS"
    elif g1_status == "PASS" and g2_status == "PASS":
        regular_edge_continuity_status = "PASS"
    corner_g1_status = "NOT_MEASURED"
    corner_g2_status = "NOT_MEASURED"
    if measured_count:
        corner_g1_status = (
            "PASS"
            if maximum_corner_normal_angle <= 5.0
            else "MEASURED_DISCONTINUOUS"
        )
        corner_g2_status = (
            "PASS"
            if maximum_corner_normal_angle <= 5.0
            and maximum_corner_curvature_mismatch <= 0.35
            else "MEASURED_DISCONTINUOUS"
        )
        if unmeasured_count and corner_g1_status == "PASS":
            corner_g1_status = "PARTIAL_PASS"
        if unmeasured_count and corner_g2_status == "PASS":
            corner_g2_status = "PARTIAL_PASS"
    corner_coupling_status = "NOT_MEASURED"
    if "MEASURED_DISCONTINUOUS" in {corner_g1_status, corner_g2_status}:
        corner_coupling_status = "FAIL"
    elif "PARTIAL_PASS" in {corner_g1_status, corner_g2_status}:
        corner_coupling_status = "PARTIAL_PASS"
    elif corner_g1_status == "PASS" and corner_g2_status == "PASS":
        corner_coupling_status = "PASS"
    continuity_status = "NOT_MEASURED"
    if "FAIL" in {
        regular_edge_continuity_status,
        corner_coupling_status,
    }:
        continuity_status = "FAIL"
    elif "PARTIAL_PASS" in {
        regular_edge_continuity_status,
        corner_coupling_status,
    }:
        continuity_status = "PARTIAL_PASS"
    elif (
        regular_edge_continuity_status == "PASS"
        and corner_coupling_status == "PASS"
    ):
        continuity_status = "PASS"
    return {
        "contract_id": "impeller_v1_1_6_attachment_topology_r16_24",
        "status": "PASS" if not unowned else "FAIL",
        "measurement_authority": (
            "authenticated_step_source_edge_identity_and_arc_length_samples"
            if require_source_identity
            else "arc_length_resampled_geometry"
        ),
        "tolerance_mm": tolerance,
        "source_boundary_record_count": len(candidates),
        "candidate_group_count": len(candidate_groups),
        "geometric_candidate_pair_count": geometric_candidate_pair_count,
        "exhaustive_candidate_pair_count": (
            len(candidates) * (len(candidates) - 1) // 2
        ),
        "matched_shared_edge_count": len(shared_edges),
        "unowned_blade_side_source_boundary_count": len(unowned),
        "unowned_blade_side_source_boundaries": unowned,
        "max_coordinate_gap_mm": maximum_gap,
        "orientation_mismatch_count": 0,
        "measured_differential_shared_edge_count": measured_count,
        "unmeasured_differential_shared_edge_count": unmeasured_count,
        "max_normal_angle_deg": maximum_normal_angle,
        "max_endpoint_corner_normal_angle_deg": maximum_corner_normal_angle,
        "max_curvature_proxy_mismatch": maximum_curvature_mismatch,
        "max_endpoint_corner_curvature_proxy_mismatch": (
            maximum_corner_curvature_mismatch
        ),
        "g1_measurement_status": g1_status,
        "g2_measurement_status": g2_status,
        "corner_g1_measurement_status": corner_g1_status,
        "corner_g2_measurement_status": corner_g2_status,
        "regular_edge_continuity_status": regular_edge_continuity_status,
        "corner_coupling_status": corner_coupling_status,
        "continuity_status": continuity_status,
        "shared_edges": shared_edges,
    }


def _arc_length_boundary_gap(
    first: np.ndarray, second: np.ndarray, *, sample_count: int = 65
) -> tuple[float, str]:
    first_samples = _resample_polyline(first, sample_count)
    second_samples = _resample_polyline(second, sample_count)
    forward = float(np.max(np.linalg.norm(first_samples - second_samples, axis=1)))
    reversed_gap = float(
        np.max(np.linalg.norm(first_samples - second_samples[::-1], axis=1))
    )
    return (
        (forward, "same")
        if forward <= reversed_gap
        else (reversed_gap, "reversed")
    )


def _matched_edge_continuity(
    first_record: Mapping[str, Any],
    second_record: Mapping[str, Any],
    first_surface: Mapping[str, Any],
    first_edge_role: str,
    second_surface: Mapping[str, Any],
    second_edge_role: str,
    *,
    orientation: str,
) -> dict[str, Any]:
    first = _record_differential_samples(first_record)
    second = _record_differential_samples(second_record)
    if first is None or second is None:
        first = _edge_differential_samples(first_surface, first_edge_role)
        second = _edge_differential_samples(second_surface, second_edge_role)
    if first is None or second is None:
        return {
            "differential_measurement_status": "NOT_MEASURED",
            "normal_angle_max_deg": None,
            "curvature_proxy_mismatch_max": None,
        }
    first_normal, first_curvature = first
    second_normal, second_curvature = second
    sample_count = 33
    first_normal = _resample_vector_sequence(first_normal, sample_count)
    second_normal = _resample_vector_sequence(second_normal, sample_count)
    first_curvature = _resample_scalar(first_curvature, sample_count)
    second_curvature = _resample_scalar(second_curvature, sample_count)
    if orientation == "reversed":
        second_normal = second_normal[::-1]
        second_curvature = second_curvature[::-1]
    first_normal /= np.maximum(
        np.linalg.norm(first_normal, axis=1)[:, None], 1.0e-18
    )
    second_normal /= np.maximum(
        np.linalg.norm(second_normal, axis=1)[:, None], 1.0e-18
    )
    dots = np.clip(np.abs(np.sum(first_normal * second_normal, axis=1)), 0.0, 1.0)
    angles = np.degrees(np.arccos(dots))
    mismatch = np.abs(first_curvature - second_curvature) / np.maximum(
        np.maximum(np.abs(first_curvature), np.abs(second_curvature)), 1.0e-9
    )
    endpoint_margin = max(2, int(math.ceil(0.125 * sample_count)))
    interior = slice(endpoint_margin, sample_count - endpoint_margin)
    endpoint_angles = np.concatenate(
        [angles[:endpoint_margin], angles[-endpoint_margin:]]
    )
    endpoint_mismatch = np.concatenate(
        [mismatch[:endpoint_margin], mismatch[-endpoint_margin:]]
    )
    return {
        "differential_measurement_status": "MEASURED",
        "normal_angle_max_deg": float(np.max(angles)),
        "normal_angle_interior_max_deg": float(np.max(angles[interior])),
        "normal_angle_endpoint_max_deg": float(np.max(endpoint_angles)),
        "curvature_proxy_mismatch_max": float(np.max(mismatch)),
        "curvature_proxy_mismatch_interior_max": float(
            np.max(mismatch[interior])
        ),
        "curvature_proxy_mismatch_endpoint_max": float(
            np.max(endpoint_mismatch)
        ),
    }


def _record_differential_samples(
    record: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray] | None:
    normals = np.asarray(record.get("surface_normal_samples"), dtype=float)
    curvature = np.asarray(
        record.get("transverse_normal_curvature_samples_per_mm"), dtype=float
    )
    if (
        normals.ndim != 2
        or normals.shape[1] != 3
        or len(normals) < 2
        or curvature.ndim != 1
        or len(curvature) != len(normals)
        or np.any(~np.isfinite(normals))
        or np.any(~np.isfinite(curvature))
    ):
        return None
    return normals, curvature


def _edge_differential_samples(
    surface: Mapping[str, Any], edge_role: str
) -> tuple[np.ndarray, np.ndarray] | None:
    grid = np.asarray(surface.get("uv_grid"), dtype=float)
    if grid.ndim != 3 or grid.shape[0] < 3 or grid.shape[1] < 3:
        return None
    if edge_role == "u_start":
        boundary, first, second = grid[0], grid[1], grid[2]
    elif edge_role == "u_end":
        boundary, first, second = grid[-1], grid[-2], grid[-3]
    elif edge_role == "v_start":
        boundary, first, second = grid[:, 0], grid[:, 1], grid[:, 2]
    elif edge_role == "v_end":
        boundary, first, second = grid[:, -1], grid[:, -2], grid[:, -3]
    else:
        return None
    tangent = np.gradient(boundary, axis=0)
    inward = first - boundary
    normal = np.cross(tangent, inward)
    first_length = np.linalg.norm(inward, axis=1)
    curvature = np.linalg.norm(second - 2.0 * first + boundary, axis=1) / np.maximum(
        first_length * first_length, 1.0e-12
    )
    return normal, curvature


def _resample_scalar(values: np.ndarray, sample_count: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(values) == sample_count:
        return values
    return np.interp(
        np.linspace(0.0, 1.0, sample_count),
        np.linspace(0.0, 1.0, len(values)),
        values,
    )


def _resample_vector_sequence(
    values: np.ndarray, sample_count: int
) -> np.ndarray:
    vectors = np.asarray(values, dtype=float)
    if len(vectors) == sample_count:
        return vectors
    source = np.linspace(0.0, 1.0, len(vectors))
    query = np.linspace(0.0, 1.0, sample_count)
    return np.column_stack(
        [np.interp(query, source, vectors[:, axis]) for axis in range(vectors.shape[1])]
    )


def _remove_superseded_surface_failures(
    graph: dict[str, Any],
    replaced_surface_ids: set[str],
    *,
    replacement_topology: Mapping[str, Any] | None = None,
) -> None:
    superseded_reasons = {
        "v1_1_root_attachment_failed",
        "v1_1_root_material_side_failed",
        "v1_1_tip_surface_failed",
        "v1_1_tip_continuity_failed",
        "v1_1_tip_domain_exceeded",
    }
    retained = []
    for failure in graph.get("transition_failures", ()) or ():
        if not isinstance(failure, Mapping):
            retained.append(failure)
            continue
        surface_id = str(
            failure.get("surface_id") or failure.get("surface_graph_id") or ""
        )
        replacement_topology_passed = (
            replacement_topology is not None
            and replacement_topology.get("status") == "PASS"
        )
        replacement_continuity_passed = (
            replacement_topology_passed
            and replacement_topology.get("continuity_status") == "PASS"
        )
        reason = str(failure.get("reason"))
        replacement_measured = (
            replacement_continuity_passed
            if reason == "v1_1_tip_continuity_failed"
            else replacement_topology_passed
        )
        if (
            surface_id in replaced_surface_ids
            and reason in superseded_reasons
            and replacement_measured
        ):
            continue
        retained.append(failure)
    graph["transition_failures"] = retained
    status = "PASS" if not retained else "FAIL"
    graph["geometry_generation_status"] = status
    graph["surface_graph_status"] = status


def _active_span_authority(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_invalid",
            "direct section population lacks active-span support authority",
        )
    hub = value.get("hub_points_rz_mm")
    if not isinstance(hub, list) or len(hub) < 2:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_invalid",
            "direct section population lacks authenticated hub support",
        )
    return value


def _closed_loop_from_grids(
    grids: Mapping[str, Sequence[Sequence[Sequence[float]]]], row_index: int
) -> list[list[float]]:
    rows = {role: [list(point) for point in grid[row_index]] for role, grid in grids.items()}
    required = {"side_a", "side_b", "leading_edge", "trailing_edge"}
    if set(rows) != required:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_role_invalid",
            "direct attachment requires side_a, side_b, leading_edge and trailing_edge curves",
        )
    result = [*rows["side_a"]]
    result.extend(rows["trailing_edge"][1:])
    result.extend(reversed(rows["side_b"][:-1]))
    result.extend(rows["leading_edge"][1:])
    if math.dist(result[0], result[-1]) > 1.0e-7:
        result.append(copy.deepcopy(result[0]))
    else:
        result[-1] = copy.deepcopy(result[0])
    return result


def _support_loop_from_carrier(
    blade_loop: Sequence[Sequence[float]],
    carrier_profile_rz_mm: Sequence[Sequence[float]],
    support_profile_rz_mm: Sequence[Sequence[float]],
) -> list[list[float]]:
    carrier = np.asarray(carrier_profile_rz_mm, dtype=float)
    support = np.asarray(support_profile_rz_mm, dtype=float)
    if carrier.ndim != 2 or support.ndim != 2 or carrier.shape[1:] != (2,) or support.shape[1:] != (2,):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_invalid",
            "carrier and support profiles must be finite R-Z point tables",
        )
    carrier_distance = np.concatenate(
        [[0.0], np.cumsum(np.linalg.norm(np.diff(carrier, axis=0), axis=1))]
    )
    support_distance = np.concatenate(
        [[0.0], np.cumsum(np.linalg.norm(np.diff(support, axis=0), axis=1))]
    )
    if carrier_distance[-1] <= 1.0e-12 or support_distance[-1] <= 1.0e-12:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_invalid",
            "carrier and support profiles must have positive meridional length",
        )
    result = []
    for point in np.asarray(blade_loop, dtype=float):
        radius = float(math.hypot(point[0], point[1]))
        rz = np.asarray([radius, point[2]], dtype=float)
        carrier_fraction = _nearest_polyline_fraction(
            rz, carrier, carrier_distance
        )
        support_target = carrier_fraction * support_distance[-1]
        support_r, support_z = (
            float(np.interp(support_target, support_distance, support[:, column]))
            for column in range(2)
        )
        theta = math.atan2(float(point[1]), float(point[0]))
        result.append(
            [
                float(support_r * math.cos(theta)),
                float(support_r * math.sin(theta)),
                float(support_z),
            ]
        )
    return result


def _nearest_polyline_fraction(
    point: np.ndarray, polyline: np.ndarray, cumulative_distance: np.ndarray
) -> float:
    best_distance = math.inf
    best_along = 0.0
    for index, (first, second) in enumerate(zip(polyline[:-1], polyline[1:])):
        vector = second - first
        length_sq = float(np.dot(vector, vector))
        fraction = (
            0.0
            if length_sq <= 1.0e-18
            else float(np.clip(np.dot(point - first, vector) / length_sq, 0.0, 1.0))
        )
        projection = first + fraction * vector
        distance = float(np.linalg.norm(point - projection))
        along = float(
            cumulative_distance[index]
            + fraction * (cumulative_distance[index + 1] - cumulative_distance[index])
        )
        if (distance, along) < (best_distance, best_along):
            best_distance = distance
            best_along = along
    return best_along / float(cumulative_distance[-1])


def _attachment_rows(
    support_loop: Sequence[Sequence[float]],
    blade_loop: Sequence[Sequence[float]],
    *,
    row_count: int,
) -> list[list[list[float]]]:
    support = np.asarray(support_loop, dtype=float)
    blade = np.asarray(blade_loop, dtype=float)
    if support.shape != blade.shape or support.ndim != 2 or support.shape[1] != 3:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_invalid",
            "attachment boundary loops must have identical finite XYZ samples",
        )
    rows = []
    for value in np.linspace(0.0, 1.0, max(7, int(row_count))):
        blend = value**3 * (10.0 + value * (-15.0 + 6.0 * value))
        rows.append((support + blend * (blade - support)).tolist())
    rows[0] = support.tolist()
    rows[-1] = blade.tolist()
    return rows


def _attachment_rows_through_boundary(
    support_loop: Sequence[Sequence[float]],
    retained_loop: Sequence[Sequence[float]],
    blade_loop: Sequence[Sequence[float]],
    *,
    row_count: int,
) -> tuple[list[list[list[float]]], int]:
    support = np.asarray(support_loop, dtype=float)
    retained = np.asarray(retained_loop, dtype=float)
    blade = np.asarray(blade_loop, dtype=float)
    if (
        support.shape != retained.shape
        or support.shape != blade.shape
        or support.ndim != 2
        or support.shape[1] != 3
        or not np.all(np.isfinite(np.stack((support, retained, blade))))
    ):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_invalid",
            "support, retained and measurement-carrier loops must share finite XYZ samples",
        )
    first_length = float(np.mean(np.linalg.norm(retained - support, axis=1)))
    second_length = float(np.mean(np.linalg.norm(blade - retained, axis=1)))
    total_length = first_length + second_length
    if total_length <= 1.0e-12:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_invalid",
            "root attachment anchors collapse to one loop",
        )
    retained_parameter = float(np.clip(first_length / total_length, 0.15, 0.85))
    intervals = max(8, int(row_count) - 1)
    left_intervals = int(np.clip(round(intervals * retained_parameter), 3, intervals - 3))
    right_intervals = intervals - left_intervals
    parameters = np.concatenate(
        (
            np.linspace(0.0, retained_parameter, left_intervals + 1),
            np.linspace(retained_parameter, 1.0, right_intervals + 1)[1:],
        )
    )
    anchors = np.stack((support, retained, blade), axis=0)
    rows = PchipInterpolator(
        [0.0, retained_parameter, 1.0],
        anchors,
        axis=0,
    )(parameters)
    rows[0] = support
    rows[left_intervals] = retained
    rows[-1] = blade
    return rows.tolist(), left_intervals


def _coons_tip_grid(
    grids: Mapping[str, Sequence[Sequence[Sequence[float]]]], row_index: int
) -> list[list[list[float]]]:
    side_a = np.asarray(grids["side_a"][row_index], dtype=float)
    side_b = np.asarray(grids["side_b"][row_index], dtype=float)
    if side_a.shape != side_b.shape:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_attachment_invalid",
            "open-tip pressure and suction boundaries lack common stream correspondence",
            {
                "pressure_boundary_sample_count": len(side_a),
                "suction_boundary_sample_count": len(side_b),
            },
        )
    leading = _resample_polyline(grids["leading_edge"][row_index], 33)[::-1]
    trailing = _resample_polyline(grids["trailing_edge"][row_index], 33)
    c00, c01 = side_a[0], side_a[-1]
    c10, c11 = side_b[0], side_b[-1]
    rows = []
    for row_index, u in enumerate(np.linspace(0.0, 1.0, len(leading))):
        row = []
        for column_index, v in enumerate(np.linspace(0.0, 1.0, len(side_a))):
            side_blend = (1.0 - u) * side_a[column_index] + u * side_b[column_index]
            edge_blend = (1.0 - v) * leading[row_index] + v * trailing[row_index]
            corner = (
                (1.0 - u) * (1.0 - v) * c00
                + (1.0 - u) * v * c01
                + u * (1.0 - v) * c10
                + u * v * c11
            )
            row.append((side_blend + edge_blend - corner).tolist())
        rows.append(row)
    rows[0] = side_a.tolist()
    rows[-1] = side_b.tolist()
    for row_index in range(len(rows)):
        rows[row_index][0] = leading[row_index].tolist()
        rows[row_index][-1] = trailing[row_index].tolist()
    return rows


def _resample_polyline(points: Sequence[Sequence[float]], count: int) -> np.ndarray:
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[0] < 2 or array.shape[1] not in {2, 3} or np.any(~np.isfinite(array)):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_contract_invalid",
            "canonical curve must contain at least two finite XYZ points",
        )
    distance = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(array, axis=0), axis=1))])
    if distance[-1] <= 1.0e-12:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_contract_invalid",
            "canonical curve has zero length",
        )
    query = np.linspace(0.0, distance[-1], count)
    return np.column_stack(
        [np.interp(query, distance, array[:, axis]) for axis in range(array.shape[1])]
    )


def _resample_authoritative_curve(
    curve: Mapping[str, Any],
    role: str,
    count: int,
    *,
    correspondence_parameter: np.ndarray | None = None,
    query: np.ndarray | None = None,
) -> np.ndarray:
    points = np.asarray(curve["canonical_points_xyz_mm"], dtype=float)
    if role not in {"side_a", "side_b"}:
        return _resample_polyline(points, count)
    curve_u = np.asarray(
        curve.get("u")
        if correspondence_parameter is None
        else correspondence_parameter,
        dtype=float,
    )
    if (
        curve_u.ndim != 1
        or len(curve_u) != len(points)
        or np.any(~np.isfinite(curve_u))
        or np.any(np.diff(curve_u) <= 0.0)
    ):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_parameter_invalid",
            f"{role} must retain a strictly increasing local curve parameter u",
        )
    query_values = (
        np.linspace(float(curve_u[0]), float(curve_u[-1]), count)
        if query is None
        else np.asarray(query, dtype=float)
    )
    return np.asarray(
        PchipInterpolator(curve_u, points, axis=0)(query_values), dtype=float
    )


def _closure_mode(stations: Sequence[Mapping[str, Any]]) -> str:
    modes = {
        str(
            station.get(
                "closure_classification", "measured_transition_curve"
            )
        )
        for station in stations
    }
    shared_trim = _authenticated_shared_trim_boundary_evidence(stations)
    if (
        shared_trim is not None
        and shared_trim["shared_boundary_count"] >= 2
        and modes.issubset(
            {"sharp_shared_seam", "endpoint_witness_bridge_review_only"}
        )
    ):
        return "sharp_shared_seam"
    if len(modes) != 1:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_closure_inconsistent",
            "section stations disagree on finite-edge versus sharp-seam topology",
            {
                "station_modes": [
                    {
                        "active_h": float(station.get("active_h", 0.0)),
                        "closure_classification": str(
                            station.get(
                                "closure_classification",
                                "measured_transition_curve",
                            )
                        ),
                        "endpoint_stagger": copy.deepcopy(
                            station.get("endpoint_stagger", {})
                        ),
                    }
                    for station in stations
                ],
                "authenticated_shared_trim_boundary_evidence": shared_trim,
            },
        )
    mode = modes.pop()
    if mode not in {
        "sharp_shared_seam",
        "finite_edge_face",
        "measured_transition_curve",
        "endpoint_witness_bridge_review_only",
    }:
        raise DirectSectionSurfaceError(
            "v116_direct_curve_closure_invalid",
            f"unsupported closure classification {mode!r}",
        )
    return mode


def _authenticated_shared_trim_boundary_evidence(
    stations: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    side_a = _common_source_surface_authority(stations, "side_a")
    side_b = _common_source_surface_authority(stations, "side_b")
    if side_a is None or side_b is None:
        return None
    paths_a = [
        _evaluate_source_face_surface(side_a, path)
        for path in _trim_boundary_paths(side_a)
    ]
    paths_b = [
        _evaluate_source_face_surface(side_b, path)
        for path in _trim_boundary_paths(side_b)
    ]
    tolerance = max(
        5.0
        * max(
            [
                float(station.get("source_tolerance_mm", 0.0))
                for station in stations
            ]
            or [0.0]
        ),
        1.0e-6,
    )
    candidates = []
    for index_a, path_a in enumerate(paths_a):
        for index_b, path_b in enumerate(paths_b):
            gap = _symmetric_polyline_hausdorff_mm(path_a, path_b)
            if gap <= tolerance:
                candidates.append((gap, index_a, index_b))
    matches = []
    used_a: set[int] = set()
    used_b: set[int] = set()
    for gap, index_a, index_b in sorted(candidates):
        if index_a in used_a or index_b in used_b:
            continue
        used_a.add(index_a)
        used_b.add(index_b)
        matches.append(
            {
                "side_a_trim_index": index_a,
                "side_b_trim_index": index_b,
                "hausdorff_mm": float(gap),
            }
        )
    return {
        "method": "authenticated_source_face_shared_trim_boundaries",
        "side_a_source_face_id": str(side_a.get("source_face_id", "")),
        "side_b_source_face_id": str(side_b.get("source_face_id", "")),
        "tolerance_mm": tolerance,
        "shared_boundary_count": len(matches),
        "matches": matches,
    }


def _symmetric_polyline_hausdorff_mm(
    first: np.ndarray, second: np.ndarray
) -> float:
    first_points = np.asarray(first, dtype=float)
    second_points = np.asarray(second, dtype=float)
    distances = np.linalg.norm(
        first_points[:, None, :] - second_points[None, :, :], axis=2
    )
    return max(
        float(np.max(np.min(distances, axis=1))),
        float(np.max(np.min(distances, axis=0))),
    )


def _rigid_matrix(value: Any) -> np.ndarray:
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != (4, 4) or np.any(~np.isfinite(matrix)):
        raise DirectSectionSurfaceError(
            "v116_direct_curve_transform_invalid",
            "periodic instance transform must be a finite 4x4 matrix",
        )
    return matrix


def _transform_grid(
    grid: Sequence[Sequence[Sequence[float]]], matrix: np.ndarray
) -> list[list[list[float]]]:
    points = np.asarray(grid, dtype=float)
    flat = points.reshape(-1, 3)
    homogeneous = np.column_stack([flat, np.ones(len(flat), dtype=float)])
    transformed = (matrix @ homogeneous.T).T[:, :3].reshape(points.shape)
    return transformed.tolist()
