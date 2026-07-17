from __future__ import annotations

from typing import Any, Mapping, Sequence


COMPARISON_SCOPE_CONTRACT_ID = (
    "impeller_v1_1_6_supported_surface_comparison_scope_v6"
)

SURFACE_LEDGER_CONTRACT_ID = (
    "impeller_v1_1_6_reconstruction_surface_comparison_ledger_v1"
)

_SUPPORTED_ROLES = {
    "hub_flowpath_support": "hub_flowpath",
    "inner_shroud_flowpath_support": "shroud_inner_flowpath",
    "outer_shroud_material_support": "shroud_outer_material",
    "periodic_blade_tip_attachment": "blade_tip_attachment",
    "periodic_blade_tip_cap": "blade_tip",
    "periodic_blade_root_attachment": "blade_root_attachment",
    "periodic_blade_side": "blade_sides",
    "periodic_blade_leading_edge": "blade_leading_edge",
    "periodic_blade_trailing_edge": "blade_trailing_edge",
}


def build_supported_surface_comparison_scope(
    source_face_semantics: Sequence[Mapping[str, Any]],
    *,
    measurements: Mapping[str, Any],
    topology_mode: str,
    expected_periodic_instance_count: int,
    periodic_populations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Partition source faces and prove required topology-role coverage."""

    records = [dict(item) for item in source_face_semantics]
    source_ids = [str(item.get("source_face_id", "")) for item in records]
    if not source_ids:
        return _rejected_scope("empty_source_face_inventory")
    if topology_mode not in {"open", "closed"}:
        return _rejected_scope("unsupported_topology_mode")
    if (
        not isinstance(expected_periodic_instance_count, int)
        or isinstance(expected_periodic_instance_count, bool)
        or expected_periodic_instance_count <= 0
    ):
        return _rejected_scope("invalid_expected_periodic_instance_count")

    if any(not value for value in source_ids) or len(set(source_ids)) != len(source_ids):
        return _rejected_scope("duplicate_source_face_assignment")

    periodic_instance_ids = sorted(
        {
            str(record["periodic_instance_id"])
            for record in records
            if record.get("periodic_instance_id") not in {None, ""}
        },
        key=_periodic_instance_sort_key,
    )
    (
        authenticated_bindings,
        expected_instances_by_population,
        binding_failure,
    ) = _validated_periodic_instance_bindings(
        periodic_populations,
        expected_periodic_instance_count=expected_periodic_instance_count,
    )
    if binding_failure is not None:
        return _rejected_scope(binding_failure, source_face_count=len(source_ids))
    if authenticated_bindings:
        if set(periodic_instance_ids) - set(authenticated_bindings):
            return _rejected_scope(
                "periodic_instance_membership_unresolved",
                source_face_count=len(source_ids),
            )
        population_by_instance = {
            instance_id: authenticated_bindings[instance_id]
            for instance_id in periodic_instance_ids
        }
    else:
        population_by_instance = {
            instance_id: {
                "population": _population_from_instance_id(instance_id),
                "lattice_index": None,
            }
            for instance_id in periodic_instance_ids
        }
    fallback_indexes: dict[str, int] = {}
    for population in sorted(
        {str(item["population"]) for item in population_by_instance.values()}
    ):
        population_ids = sorted(
            (
                instance_id
                for instance_id, binding in population_by_instance.items()
                if binding["population"] == population
            ),
            key=_periodic_instance_sort_key,
        )
        fallback_indexes.update(
            {instance_id: index for index, instance_id in enumerate(population_ids)}
        )

    requested_mounting_bore_ids = _source_face_ids(
        _material_measurement(measurements, "mounting_bore_radius_mm")
    )
    requested_bottom_ids = _bottom_source_face_ids(
        _material_measurement(measurements, "hub_bottom_thickness_mm")
    )
    requested_hub_material_ids = _hub_material_component_source_face_ids(
        _material_measurement(measurements, "hub_bottom_thickness_mm")
    )
    known_ids = set(source_ids)
    mounting_bore_ids = requested_mounting_bore_ids & known_ids
    bottom_ids = requested_bottom_ids & known_ids
    hub_material_ids = requested_hub_material_ids & known_ids
    if requested_bottom_ids - known_ids:
        return _rejected_scope(
            "hub_bottom_source_face_unresolved",
            source_face_count=len(source_ids),
        )

    included = []
    excluded = []
    for record in sorted(records, key=lambda item: str(item["source_face_id"])):
        source_face_id = str(record["source_face_id"])
        semantic_role = str(record.get("semantic_role", "source_material_boundary"))
        base = {
            "source_face_id": source_face_id,
            "semantic_role": semantic_role,
            "source_role_hint": str(record.get("source_role_hint", "")),
            "geometry_type": str(record.get("geometry_type", "")),
            "periodic_instance_id": record.get("periodic_instance_id"),
        }
        if source_face_id in bottom_ids:
            excluded.append(
                {
                    **base,
                    "comparison_status": "non_comparable",
                    "reason": "unsupported_nonplanar_hub_bottom_or_boss",
                    "permitted_use": "axis_and_topology_evidence_only",
                }
            )
            continue
        if source_face_id in mounting_bore_ids:
            excluded.append(
                {
                    **base,
                    "comparison_status": "non_comparable",
                    "reason": "v116_shaft_interface_spline_unsupported",
                    "permitted_use": "axis_and_topology_evidence_only",
                }
            )
            continue
        exclusion_reason = _exclusion_reason(record)
        reconstruction_role = _SUPPORTED_ROLES.get(semantic_role)
        if exclusion_reason != "unsupported_local_material_feature":
            excluded.append(
                {
                    **base,
                    "comparison_status": "non_comparable",
                    "reason": exclusion_reason,
                    "permitted_use": "axis_and_topology_evidence_only",
                }
            )
            continue
        if (
            reconstruction_role is None
            and source_face_id in hub_material_ids
            and base["periodic_instance_id"] in {None, ""}
        ):
            reconstruction_role = "hub_material_closure"
        if reconstruction_role is not None:
            instance_id = base["periodic_instance_id"]
            if instance_id not in {None, ""}:
                binding = population_by_instance[str(instance_id)]
                lattice_index = binding.get("lattice_index")
                if lattice_index is None:
                    lattice_index = fallback_indexes[str(instance_id)]
                base["comparison_region_id"] = (
                    f"{reconstruction_role}::{instance_id}"
                )
                base["periodic_population"] = str(binding["population"])
                base["periodic_lattice_index"] = int(lattice_index)
                base["reconstruction_blade_pair_index"] = int(lattice_index)
                base["reconstruction_blade_index"] = int(lattice_index)
            else:
                base["comparison_region_id"] = reconstruction_role
            included.append(
                {
                    **base,
                    "comparison_status": "included",
                    "reconstruction_role": reconstruction_role,
                    "authority": (
                        "support_bound_hub_material_component_review_union"
                        if reconstruction_role == "hub_material_closure"
                        else "task3_source_solid_semantic_partition"
                    ),
                }
            )
            continue
        excluded.append(
            {
                **base,
                "comparison_status": "non_comparable",
                "reason": _exclusion_reason(record),
                "permitted_use": "axis_and_topology_evidence_only",
            }
        )

    _exclude_incomplete_periodic_edge_roles(
        included,
        excluded,
        expected_periodic_instance_count=expected_periodic_instance_count,
        expected_instances_by_population=expected_instances_by_population,
    )
    included_ids = sorted(item["source_face_id"] for item in included)
    excluded_ids = sorted(item["source_face_id"] for item in excluded)
    complete = (
        len(included_ids) + len(excluded_ids) == len(source_ids)
        and set(included_ids).isdisjoint(excluded_ids)
        and set(included_ids) | set(excluded_ids) == set(source_ids)
    )
    required_roles = {
        "hub_flowpath",
        "blade_sides",
        "blade_root_attachment",
        "blade_tip" if topology_mode == "open" else "blade_tip_attachment",
        "blade_leading_edge",
        "blade_trailing_edge",
    }
    if topology_mode == "closed":
        required_roles.update({"shroud_inner_flowpath", "shroud_outer_material"})
    included_roles = {
        str(item["reconstruction_role"]) for item in included
    }
    missing_roles = sorted(required_roles - included_roles)
    periodic_roles = sorted(
        role
        for role in required_roles
        if role
        in {
            "blade_sides",
            "blade_root_attachment",
            "blade_tip",
            "blade_tip_attachment",
            "blade_leading_edge",
            "blade_trailing_edge",
        }
    )
    periodic_coverage = {}
    periodic_population_coverage = {}
    authenticated_instance_ids = set(authenticated_bindings)
    for role in periodic_roles:
        role_records = [
            item for item in included if item["reconstruction_role"] == role
        ]
        instance_id_set = {
            str(item["periodic_instance_id"])
            for item in role_records
            if item.get("periodic_instance_id") not in {None, ""}
        }
        instance_ids = sorted(instance_id_set)
        periodic_coverage[role] = {
            "expected_count": expected_periodic_instance_count,
            "observed_count": len(instance_ids),
            "periodic_instance_ids": instance_ids,
            "complete": (
                instance_id_set == authenticated_instance_ids
                if authenticated_instance_ids
                else len(instance_ids) == expected_periodic_instance_count
            ),
        }
        periodic_population_coverage[role] = {}
        for population, expected_ids in expected_instances_by_population.items():
            observed_ids = {
                str(item["periodic_instance_id"])
                for item in role_records
                if item.get("periodic_population") == population
                and item.get("periodic_instance_id") not in {None, ""}
            }
            periodic_population_coverage[role][population] = {
                "expected_count": len(expected_ids),
                "observed_count": len(observed_ids),
                "expected_instance_ids": sorted(expected_ids),
                "periodic_instance_ids": sorted(observed_ids),
                "complete": observed_ids == expected_ids,
            }
    periodic_complete = all(
        record["complete"] for record in periodic_coverage.values()
    )
    incomplete_periodic_roles = {
        role for role, record in periodic_coverage.items() if not record["complete"]
    }
    has_periodic_surface_evidence = any(
        record["observed_count"] > 0 for record in periodic_coverage.values()
    )
    measured_periodic_complete = incomplete_periodic_roles <= {
        "blade_leading_edge",
        "blade_trailing_edge",
    }
    unresolved_closures = [
        record
        for record in excluded
        if record.get("reason") == "unresolved_blade_closure_correspondence"
    ]
    unresolved_edge_roles = {"blade_leading_edge", "blade_trailing_edge"}
    only_unresolved_edges_missing = set(missing_roles) <= unresolved_edge_roles
    if complete and not missing_roles and periodic_complete:
        status = "PASS"
    elif (
        complete
        and measured_periodic_complete
        and only_unresolved_edges_missing
        and unresolved_closures
    ):
        status = "PARTIAL_REVIEW"
    else:
        status = "REJECTED"
    failure_reason = None
    if not complete:
        failure_reason = "source_face_partition_incomplete"
    elif status == "PARTIAL_REVIEW":
        failure_reason = "unresolved_blade_closure_correspondence"
    elif has_periodic_surface_evidence and not measured_periodic_complete:
        failure_reason = "periodic_instance_coverage_incomplete"
    elif missing_roles:
        failure_reason = "required_comparison_roles_missing"
    elif not periodic_complete:
        failure_reason = "periodic_instance_coverage_incomplete"
    return {
        "contract_id": COMPARISON_SCOPE_CONTRACT_ID,
        "status": status,
        "coverage_complete": complete,
        "comparison_coverage_complete": status == "PASS",
        "failure_reason": failure_reason,
        "topology_mode": topology_mode,
        "required_roles": sorted(required_roles),
        "missing_required_roles": missing_roles,
        "expected_periodic_instance_count": expected_periodic_instance_count,
        "periodic_instance_coverage": periodic_coverage,
        "periodic_population_coverage": periodic_population_coverage,
        "periodic_coverage_complete": periodic_complete,
        "measured_periodic_coverage_complete": measured_periodic_complete,
        "partial_review_reasons": (
            ["unresolved_blade_closure_correspondence"]
            if status == "PARTIAL_REVIEW"
            else []
        ),
        "comparison_direction": (
            "reconstruction_samples_to_corresponding_source_triangle_surfaces"
        ),
        "units": "mm",
        "included_surfaces": included,
        "excluded_surfaces": excluded,
        "included_source_face_ids": included_ids,
        "excluded_source_face_ids": excluded_ids,
        "source_face_count": len(source_ids),
        "included_face_count": len(included_ids),
        "excluded_face_count": len(excluded_ids),
    }


def build_reconstruction_surface_comparison_ledger(
    surface_graph: Mapping[str, Any],
    comparison_scope: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconcile every rendered material surface with comparison evidence."""

    surfaces = [
        dict(surface)
        for surface in surface_graph.get("surfaces", ())
        if isinstance(surface, Mapping)
        and surface.get("export_default") != "excluded"
        and surface.get("material") is not False
    ]
    included = [
        dict(record)
        for record in comparison_scope.get("included_surfaces", ())
        if isinstance(record, Mapping)
    ]
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for surface in surfaces:
        surface_id = str(surface.get("id", ""))
        surface_role = str(surface.get("role", ""))
        if not surface_id or surface_id in seen_ids:
            return _rejected_surface_ledger(
                surfaces,
                reason="duplicate_or_empty_reconstruction_surface_id",
            )
        seen_ids.add(surface_id)
        base = {
            "surface_id": surface_id,
            "surface_role": surface_role,
            "blade_class": surface.get("blade_class"),
            "blade_pair_index": surface.get("blade_pair_index"),
            "blade_index": _surface_blade_index(surface),
        }
        uv_grid = surface.get("uv_grid")
        if (
            not isinstance(uv_grid, list)
            or len(uv_grid) < 2
            or any(not isinstance(row, list) or len(row) < 2 for row in uv_grid)
        ):
            records.append(
                {
                    **base,
                    "disposition": "FAILED_UNRESOLVED",
                    "reason": "reconstruction_surface_uv_grid_missing",
                    "comparison_region_id": None,
                    "source_face_ids": [],
                    "acceptance_eligible": False,
                }
            )
            continue
        if surface_role == "mounting_bore" or surface_id == "mounting_bore_inner_wall_surface":
            records.append(
                {
                    **base,
                    "disposition": "EXCLUDED_NOT_EVALUATED",
                    "reason": "v116_shaft_interface_spline_unsupported",
                    "comparison_region_id": None,
                    "source_face_ids": [],
                    "acceptance_eligible": False,
                }
            )
            continue
        reconstruction_role = _surface_comparison_role(surface)
        candidates = [
            record
            for record in included
            if record.get("reconstruction_role") == reconstruction_role
            and _record_matches_surface_instance(record, surface)
        ]
        if candidates:
            region_ids = {
                str(
                    record.get("comparison_region_id")
                    or record.get("reconstruction_role")
                )
                for record in candidates
            }
            if len(region_ids) != 1:
                records.append(
                    {
                        **base,
                        "disposition": "FAILED_UNRESOLVED",
                        "reason": "ambiguous_source_comparison_region",
                        "comparison_region_id": None,
                        "source_face_ids": sorted(
                            str(record["source_face_id"]) for record in candidates
                        ),
                        "acceptance_eligible": False,
                    }
                )
                continue
            records.append(
                {
                    **base,
                    "disposition": "EVALUATED",
                    "reason": None,
                    "comparison_region_id": next(iter(region_ids)),
                    "source_face_ids": sorted(
                        str(record["source_face_id"]) for record in candidates
                    ),
                    "comparison_authority": _surface_comparison_authority(
                        surface, reconstruction_role
                    ),
                    "acceptance_eligible": (
                        reconstruction_role != "hub_material_closure"
                    ),
                }
            )
            continue
        records.append(
            {
                **base,
                "disposition": "FAILED_UNRESOLVED",
                "reason": _unresolved_surface_reason(surface),
                "comparison_region_id": None,
                "source_face_ids": [],
                "acceptance_eligible": False,
            }
        )

    counts = {
        disposition: sum(
            record["disposition"] == disposition for record in records
        )
        for disposition in (
            "EVALUATED",
            "EXCLUDED_NOT_EVALUATED",
            "FAILED_UNRESOLVED",
        )
    }
    return {
        "contract_id": SURFACE_LEDGER_CONTRACT_ID,
        "status": "PASS" if counts["FAILED_UNRESOLVED"] == 0 else "REJECTED",
        "comparison_coverage_complete": counts["FAILED_UNRESOLVED"] == 0,
        "surface_count": len(records),
        "evaluated_surface_count": counts["EVALUATED"],
        "excluded_surface_count": counts["EXCLUDED_NOT_EVALUATED"],
        "unresolved_surface_count": counts["FAILED_UNRESOLVED"],
        "surfaces": records,
    }


def _surface_comparison_role(surface: Mapping[str, Any]) -> str | None:
    surface_id = str(surface.get("id", ""))
    surface_role = str(surface.get("role", ""))
    if surface_id == "hub_support_surface":
        return "hub_flowpath"
    if surface_id == "shroud_support_surface":
        return "shroud_inner_flowpath"
    if surface_id == "shroud_outer_material_surface":
        return "shroud_outer_material"
    if surface_id in {
        "hub_top_annulus_surface",
        "hub_bottom_annulus_surface",
        "hub_bottom_outer_wall_surface",
    }:
        return "hub_material_closure"
    return {
        "blade_pressure": "blade_sides",
        "blade_suction": "blade_sides",
        "blade_leading_edge": "blade_leading_edge",
        "blade_trailing_edge": "blade_trailing_edge",
        "root_to_hub_attachment": "blade_root_attachment",
        "closed_shroud_attachment": "blade_tip_attachment",
        "open_tip_dome": "blade_tip",
    }.get(surface_role)


def _record_matches_surface_instance(
    record: Mapping[str, Any], surface: Mapping[str, Any]
) -> bool:
    instance_id = record.get("periodic_instance_id")
    if instance_id in {None, ""}:
        return _surface_blade_index(surface) is None
    blade_class = str(surface.get("blade_class", ""))
    record_class = str(record.get("periodic_population", ""))
    pair_index = surface.get("blade_pair_index")
    record_pair_index = record.get("reconstruction_blade_pair_index")
    if blade_class and record_class and pair_index is not None:
        return blade_class == record_class and int(pair_index) == int(record_pair_index)
    blade_index = _surface_blade_index(surface)
    record_blade_index = record.get("reconstruction_blade_index")
    return blade_index is not None and int(blade_index) == int(record_blade_index)


def _surface_blade_index(surface: Mapping[str, Any]) -> int | None:
    value = surface.get("blade_index")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return int(value)
    surface_id = str(surface.get("id", ""))
    if not surface_id.startswith("blade_"):
        return None
    token = surface_id[len("blade_") :].split("_", 1)[0]
    return int(token) if token.isdigit() else None


def _surface_comparison_authority(
    surface: Mapping[str, Any], reconstruction_role: str | None
) -> str:
    if str(surface.get("role", "")) in {"blade_pressure", "blade_suction"}:
        return "periodic_instance_material_boundary_union"
    if reconstruction_role == "hub_flowpath":
        return "authenticated_periodic_hub_passage_union"
    if reconstruction_role == "hub_material_closure":
        return "support_bound_hub_material_component_review_union"
    if reconstruction_role in {"blade_leading_edge", "blade_trailing_edge"}:
        return "task7_exact_shared_boundary_hub_meridional_s_partition"
    return "authenticated_source_semantic_surface_family"


def _unresolved_surface_reason(surface: Mapping[str, Any]) -> str:
    surface_id = str(surface.get("id", ""))
    if surface_id.startswith("hub_"):
        return "hub_material_surface_correspondence_unresolved"
    if str(surface.get("role", "")) in {
        "blade_leading_edge",
        "blade_trailing_edge",
    }:
        return "blade_edge_surface_correspondence_unresolved"
    return "reconstruction_surface_correspondence_unresolved"


def _rejected_surface_ledger(
    surfaces: Sequence[Mapping[str, Any]], *, reason: str
) -> dict[str, Any]:
    return {
        "contract_id": SURFACE_LEDGER_CONTRACT_ID,
        "status": "REJECTED",
        "comparison_coverage_complete": False,
        "failure_reason": reason,
        "surface_count": len(surfaces),
        "evaluated_surface_count": 0,
        "excluded_surface_count": 0,
        "unresolved_surface_count": len(surfaces),
        "surfaces": [],
    }


def _validated_periodic_instance_bindings(
    populations: Sequence[Mapping[str, Any]],
    *,
    expected_periodic_instance_count: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, set[str]], str | None]:
    if not populations:
        return {}, {}, None
    bindings: dict[str, dict[str, Any]] = {}
    expected_instances_by_population: dict[str, set[str]] = {}
    declared_instance_count = 0
    for population in populations:
        if not isinstance(population, Mapping):
            return {}, {}, "invalid_periodic_population_evidence"
        population_id = str(
            population.get("classification")
            or population.get("population_id")
            or ""
        )
        instances = population.get("instances")
        if not population_id or population_id in expected_instances_by_population:
            return {}, {}, "invalid_periodic_population_evidence"
        if not isinstance(instances, Sequence) or isinstance(instances, (str, bytes)):
            return {}, {}, "invalid_periodic_population_evidence"
        if not instances:
            return {}, {}, "invalid_periodic_population_evidence"
        declared_count = population.get("count")
        if (
            not isinstance(declared_count, int)
            or isinstance(declared_count, bool)
            or declared_count <= 0
            or declared_count != len(instances)
        ):
            return {}, {}, "invalid_periodic_population_evidence"
        population_instance_ids: set[str] = set()
        lattice_indexes: set[int] = set()
        for fallback_index, instance in enumerate(instances):
            if not isinstance(instance, Mapping):
                return {}, {}, "invalid_periodic_population_evidence"
            instance_id = str(instance.get("instance_id", ""))
            if not instance_id or instance_id in bindings:
                return {}, {}, "invalid_periodic_population_evidence"
            raw_index = instance.get("lattice_index", fallback_index)
            if not isinstance(raw_index, int) or isinstance(raw_index, bool) or raw_index < 0:
                return {}, {}, "invalid_periodic_population_evidence"
            if raw_index in lattice_indexes:
                return {}, {}, "invalid_periodic_population_evidence"
            bindings[instance_id] = {
                "population": population_id,
                "lattice_index": int(raw_index),
            }
            population_instance_ids.add(instance_id)
            lattice_indexes.add(int(raw_index))
        if lattice_indexes != set(range(declared_count)):
            return {}, {}, "invalid_periodic_population_evidence"
        expected_instances_by_population[population_id] = population_instance_ids
        declared_instance_count += declared_count
    if (
        declared_instance_count != expected_periodic_instance_count
        or len(bindings) != expected_periodic_instance_count
    ):
        return {}, {}, "periodic_population_count_mismatch"
    return bindings, expected_instances_by_population, None


def _exclude_incomplete_periodic_edge_roles(
    included: list[dict[str, Any]],
    excluded: list[dict[str, Any]],
    *,
    expected_periodic_instance_count: int,
    expected_instances_by_population: Mapping[str, set[str]],
) -> None:
    for role in ("blade_leading_edge", "blade_trailing_edge"):
        role_records = [
            record for record in included if record.get("reconstruction_role") == role
        ]
        if expected_instances_by_population:
            for population, expected_ids in expected_instances_by_population.items():
                population_records = [
                    record
                    for record in role_records
                    if record.get("periodic_population") == population
                ]
                instance_ids = {
                    str(record["periodic_instance_id"])
                    for record in population_records
                    if record.get("periodic_instance_id") not in {None, ""}
                }
                if not population_records or instance_ids == expected_ids:
                    continue
                _move_unresolved_edge_records(
                    included, excluded, population_records
                )
            continue
        instance_ids = {
            str(record["periodic_instance_id"])
            for record in role_records
            if record.get("periodic_instance_id") not in {None, ""}
        }
        if not role_records or len(instance_ids) == expected_periodic_instance_count:
            continue
        _move_unresolved_edge_records(included, excluded, role_records)


def _move_unresolved_edge_records(
    included: list[dict[str, Any]],
    excluded: list[dict[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> None:
    source_face_ids = {str(record["source_face_id"]) for record in records}
    included[:] = [
        record
        for record in included
        if str(record.get("source_face_id")) not in source_face_ids
    ]
    for record in records:
        excluded.append(
            {
                "source_face_id": record["source_face_id"],
                "semantic_role": record["semantic_role"],
                "source_role_hint": record.get("source_role_hint", ""),
                "geometry_type": record.get("geometry_type", ""),
                "periodic_instance_id": record.get("periodic_instance_id"),
                "periodic_population": record.get("periodic_population"),
                "comparison_status": "non_comparable",
                "reason": "unresolved_blade_closure_correspondence",
                "permitted_use": "axis_and_topology_evidence_only",
            }
        )


def _population_from_instance_id(instance_id: str) -> str:
    normalized = str(instance_id).lower()
    if normalized.startswith("splitter"):
        return "splitter"
    if normalized.startswith("main"):
        return "main"
    return "periodic"


def _rejected_scope(
    reason: str, *, source_face_count: int = 0
) -> dict[str, Any]:
    return {
        "contract_id": COMPARISON_SCOPE_CONTRACT_ID,
        "status": "REJECTED",
        "coverage_complete": False,
        "comparison_coverage_complete": False,
        "failure_reason": reason,
        "comparison_direction": (
            "reconstruction_samples_to_corresponding_source_triangle_surfaces"
        ),
        "units": "mm",
        "included_surfaces": [],
        "excluded_surfaces": [],
        "included_source_face_ids": [],
        "excluded_source_face_ids": [],
        "source_face_count": source_face_count,
        "included_face_count": 0,
        "excluded_face_count": 0,
    }


def _periodic_instance_sort_key(instance_id: str) -> tuple[int, int, str]:
    text = str(instance_id)
    population_rank = 0 if text.startswith("main") else 1 if text.startswith("splitter") else 2
    suffix = text.rsplit("_", 1)[-1].rsplit("-", 1)[-1]
    index = int(suffix) if suffix.isdigit() else 10**9
    return population_rank, index, text


def _material_measurement(
    measurements: Mapping[str, Any], name: str
) -> Mapping[str, Any]:
    topology = measurements.get("topology", {})
    material = topology.get("material_measurements", {}) if isinstance(topology, Mapping) else {}
    value = material.get(name, {}) if isinstance(material, Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def _source_face_ids(record: Mapping[str, Any]) -> set[str]:
    return {str(value) for value in record.get("source_ids", ())}


def _bottom_source_face_ids(record: Mapping[str, Any]) -> set[str]:
    evidence = record.get("evidence", {})
    measurement = evidence.get("measurement_evidence", {}) if isinstance(evidence, Mapping) else {}
    values = measurement.get("bottom_source_face_ids", ()) if isinstance(measurement, Mapping) else ()
    return {str(value) for value in values}


def _hub_material_component_source_face_ids(
    record: Mapping[str, Any],
) -> set[str]:
    evidence = record.get("evidence", {})
    measurement = (
        evidence.get("measurement_evidence", {})
        if isinstance(evidence, Mapping)
        else {}
    )
    values = (
        measurement.get("hub_material_component_face_ids", ())
        if isinstance(measurement, Mapping)
        else ()
    )
    return {str(value) for value in values}


def _exclusion_reason(record: Mapping[str, Any]) -> str:
    if str(record.get("semantic_role", "")) == "periodic_blade_unclassified_closure":
        return "unresolved_blade_closure_correspondence"
    hint = str(record.get("source_role_hint", "")).lower()
    if "spline" in hint or "keyway" in hint or "key_slot" in hint:
        return "unsupported_spline_or_keyway"
    if bool(record.get("hole_boundary")):
        return "unsupported_auxiliary_hole"
    return "unsupported_local_material_feature"
