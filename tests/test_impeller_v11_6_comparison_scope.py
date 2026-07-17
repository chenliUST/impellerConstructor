import sys
from pathlib import Path

# ruff: noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from part_rule_synthesis.impeller_v11_6_comparison_scope import (
    build_reconstruction_surface_comparison_ledger,
    build_supported_surface_comparison_scope,
)


def test_scope_partitions_supported_surfaces_and_explicit_exclusions():
    scope = build_supported_surface_comparison_scope(
        [
            face("hub", "hub_flowpath_support"),
            face("blade", "periodic_blade_side", periodic=True),
            face("root", "periodic_blade_root_attachment", periodic=True),
            face("tip", "periodic_blade_tip_cap", periodic=True),
            face("closure", "periodic_blade_unclassified_closure", periodic=True),
            face("center-bore", "source_material_boundary", hole=True),
            face("aux-hole", "periodic_blade_side", hole=True, periodic=True),
            face("spline", "source_material_boundary", hint="spline_slot"),
            face("bottom", "hub_flowpath_support"),
            face("boss", "periodic_blade_side", periodic=True),
        ],
        measurements={
            "topology": {
                "material_measurements": {
                    "mounting_bore_radius_mm": {
                        "source_ids": ["source_edge_1", "center-bore"]
                    },
                    "hub_bottom_thickness_mm": {
                        "evidence": {
                            "measurement_evidence": {
                                "bottom_source_face_ids": ["bottom", "boss"]
                            }
                        }
                    },
                }
            }
        },
        topology_mode="open",
        expected_periodic_instance_count=1,
    )

    assert scope["status"] == "PARTIAL_REVIEW"
    assert scope["comparison_coverage_complete"] is False
    assert scope["failure_reason"] == "unresolved_blade_closure_correspondence"
    roles = {
        record["source_face_id"]: record["reconstruction_role"]
        for record in scope["included_surfaces"]
    }
    assert roles["blade"] == "blade_sides"
    assert roles["root"] == "blade_root_attachment"
    blade_record = next(
        record
        for record in scope["included_surfaces"]
        if record["source_face_id"] == "blade"
    )
    assert blade_record["comparison_region_id"] == "blade_sides::main-01"
    assert blade_record["reconstruction_blade_index"] == 0
    excluded = {
        record["source_face_id"]: record["reason"]
        for record in scope["excluded_surfaces"]
    }
    assert excluded["closure"] == "unresolved_blade_closure_correspondence"
    assert scope["coverage_complete"] is True
    assert scope["included_source_face_ids"] == [
        "blade",
        "hub",
        "root",
        "tip",
    ]
    assert scope["excluded_source_face_ids"] == [
        "aux-hole",
        "boss",
        "bottom",
        "center-bore",
        "closure",
        "spline",
    ]
    assert set(scope["included_source_face_ids"]).isdisjoint(
        scope["excluded_source_face_ids"]
    )
    reasons = {
        record["source_face_id"]: record["reason"]
        for record in scope["excluded_surfaces"]
    }
    assert reasons == {
        "aux-hole": "unsupported_auxiliary_hole",
        "boss": "unsupported_nonplanar_hub_bottom_or_boss",
        "bottom": "unsupported_nonplanar_hub_bottom_or_boss",
        "center-bore": "v116_shaft_interface_spline_unsupported",
        "closure": "unresolved_blade_closure_correspondence",
        "spline": "unsupported_spline_or_keyway",
    }
    assert set(scope["missing_required_roles"]) == {
        "blade_leading_edge",
        "blade_trailing_edge",
    }


def test_scope_rejects_duplicate_or_incomplete_source_face_inventory():
    empty = build_supported_surface_comparison_scope(
        [], measurements={}, topology_mode="open", expected_periodic_instance_count=1
    )
    assert empty["failure_reason"] == "empty_source_face_inventory"

    duplicate = build_supported_surface_comparison_scope(
        [face("hub", "hub_flowpath_support"), face("hub", "periodic_blade_side")],
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=1,
    )
    assert duplicate["status"] == "REJECTED"
    assert duplicate["coverage_complete"] is False
    assert duplicate["failure_reason"] == "duplicate_source_face_assignment"


def test_scope_does_not_promote_unresolved_bore_provenance_to_supported_geometry():
    stale_bore = build_supported_surface_comparison_scope(
        [face("aux-hole", "source_material_boundary", hole=True)],
        measurements={
            "topology": {
                "material_measurements": {
                    "mounting_bore_radius_mm": {"source_ids": ["missing-bore"]}
                }
            }
        },
        topology_mode="open",
        expected_periodic_instance_count=1,
    )
    assert stale_bore["status"] == "REJECTED"
    assert stale_bore["failure_reason"] == "required_comparison_roles_missing"
    assert stale_bore["included_surfaces"] == []
    assert stale_bore["excluded_surfaces"][0]["reason"] == (
        "unsupported_auxiliary_hole"
    )

    stale_bottom = build_supported_surface_comparison_scope(
        [face("center-bore", "source_material_boundary", hole=True)],
        measurements={
            "topology": {
                "material_measurements": {
                    "mounting_bore_radius_mm": {"source_ids": ["center-bore"]},
                    "hub_bottom_thickness_mm": {
                        "evidence": {
                            "measurement_evidence": {
                                "bottom_source_face_ids": ["missing-bottom"]
                            }
                        }
                    },
                }
            }
        },
        topology_mode="open",
        expected_periodic_instance_count=1,
    )
    assert stale_bottom["status"] == "REJECTED"
    assert stale_bottom["failure_reason"] == "hub_bottom_source_face_unresolved"


def test_reconstruction_surface_ledger_is_face_complete_and_excludes_shaft_interface():
    scope = build_supported_surface_comparison_scope(
        [
            face("hub", "hub_flowpath_support"),
            face("blade", "periodic_blade_side", periodic=True),
            face("root", "periodic_blade_root_attachment", periodic=True),
            face("tip", "periodic_blade_tip_cap", periodic=True),
            face("leading", "periodic_blade_leading_edge", periodic=True),
            face("trailing", "periodic_blade_trailing_edge", periodic=True),
            face("center-bore", "source_material_boundary", hole=True),
        ],
        measurements={
            "topology": {
                "material_measurements": {
                    "mounting_bore_radius_mm": {"source_ids": ["center-bore"]}
                }
            }
        },
        topology_mode="open",
        expected_periodic_instance_count=1,
    )
    ledger = build_reconstruction_surface_comparison_ledger(
        {
            "surfaces": [
                surface("hub_support_surface", "hub_support"),
                surface("hub_top_annulus_surface", "hub_support"),
                surface("blade_0_pressure_surface", "blade_pressure", blade_index=0),
                surface("blade_0_suction_surface", "blade_suction", blade_index=0),
                surface("blade_0_leading_edge_surface", "blade_leading_edge", blade_index=0),
                surface("blade_0_trailing_edge_surface", "blade_trailing_edge", blade_index=0),
                surface(
                    "blade_0_root_attachment_surface",
                    "root_to_hub_attachment",
                    blade_index=0,
                ),
                surface("blade_0_open_tip_dome_surface", "open_tip_dome", blade_index=0),
                surface("mounting_bore_inner_wall_surface", "mounting_bore"),
            ]
        },
        scope,
    )

    assert ledger["surface_count"] == 9
    assert len(ledger["surfaces"]) == ledger["surface_count"]
    records = {record["surface_id"]: record for record in ledger["surfaces"]}
    assert records["hub_support_surface"]["disposition"] == "EVALUATED"
    assert records["blade_0_pressure_surface"]["comparison_region_id"] == (
        "blade_sides::main-01"
    )
    assert records["blade_0_suction_surface"]["comparison_region_id"] == (
        "blade_sides::main-01"
    )
    assert records["mounting_bore_inner_wall_surface"]["disposition"] == (
        "EXCLUDED_NOT_EVALUATED"
    )
    assert records["mounting_bore_inner_wall_surface"]["reason"] == (
        "v116_shaft_interface_spline_unsupported"
    )
    assert records["blade_0_leading_edge_surface"]["comparison_authority"] == (
        "task7_exact_shared_boundary_hub_meridional_s_partition"
    )
    assert records["blade_0_trailing_edge_surface"]["comparison_authority"] == (
        "task7_exact_shared_boundary_hub_meridional_s_partition"
    )
    assert records["hub_top_annulus_surface"]["disposition"] == "FAILED_UNRESOLVED"
    assert ledger["evaluated_surface_count"] == 7
    assert ledger["excluded_surface_count"] == 1
    assert ledger["unresolved_surface_count"] == 1
    assert ledger["comparison_coverage_complete"] is False


def test_hub_material_closure_union_provides_review_heatmap_for_each_hub_face():
    records = [
        face("hub", "hub_flowpath_support"),
        face("hub-material", "source_material_boundary"),
        face("blade", "periodic_blade_side", periodic=True),
        face("root", "periodic_blade_root_attachment", periodic=True),
        face("tip", "periodic_blade_tip_cap", periodic=True),
        face("leading", "periodic_blade_leading_edge", periodic=True),
        face("trailing", "periodic_blade_trailing_edge", periodic=True),
        face("center-bore", "source_material_boundary", hole=True),
    ]
    measurements = {
        "topology": {
            "material_measurements": {
                "mounting_bore_radius_mm": {"source_ids": ["center-bore"]},
                "hub_bottom_thickness_mm": {
                    "evidence": {
                        "measurement_evidence": {
                            "hub_material_component_face_ids": [
                                "hub",
                                "hub-material",
                                "center-bore",
                            ]
                        }
                    }
                },
            }
        }
    }
    scope = build_supported_surface_comparison_scope(
        records,
        measurements=measurements,
        topology_mode="open",
        expected_periodic_instance_count=1,
    )
    ledger = build_reconstruction_surface_comparison_ledger(
        {
            "surfaces": [
                surface("hub_support_surface", "hub_support"),
                surface("hub_top_annulus_surface", "hub_support"),
                surface("hub_bottom_annulus_surface", "hub_support"),
                surface("hub_bottom_outer_wall_surface", "hub_support"),
                surface("blade_0_pressure_surface", "blade_pressure", blade_index=0),
                surface("blade_0_suction_surface", "blade_suction", blade_index=0),
                surface(
                    "blade_0_root_attachment_surface",
                    "root_to_hub_attachment",
                    blade_index=0,
                ),
                surface(
                    "blade_0_open_tip_dome_surface",
                    "open_tip_dome",
                    blade_index=0,
                ),
                surface(
                    "blade_0_leading_edge_surface",
                    "blade_leading_edge",
                    blade_index=0,
                ),
                surface(
                    "blade_0_trailing_edge_surface",
                    "blade_trailing_edge",
                    blade_index=0,
                ),
                surface("mounting_bore_inner_wall_surface", "mounting_bore"),
            ]
        },
        scope,
    )

    hub_records = {
        record["surface_id"]: record
        for record in ledger["surfaces"]
        if record["surface_id"].startswith("hub_")
    }
    assert hub_records["hub_support_surface"]["comparison_region_id"] == (
        "hub_flowpath"
    )
    for surface_id in (
        "hub_top_annulus_surface",
        "hub_bottom_annulus_surface",
        "hub_bottom_outer_wall_surface",
    ):
        assert hub_records[surface_id]["disposition"] == "EVALUATED"
        assert hub_records[surface_id]["comparison_region_id"] == (
            "hub_material_closure"
        )
        assert hub_records[surface_id]["acceptance_eligible"] is False
    assert ledger["unresolved_surface_count"] == 0
    assert ledger["excluded_surface_count"] == 1


def test_material_surface_without_uv_grid_is_unresolved_not_silently_omitted():
    scope = build_supported_surface_comparison_scope(
        [
            face("hub", "hub_flowpath_support"),
            face("blade", "periodic_blade_side", periodic=True),
            face("root", "periodic_blade_root_attachment", periodic=True),
            face("tip", "periodic_blade_tip_cap", periodic=True),
            face("leading", "periodic_blade_leading_edge", periodic=True),
            face("trailing", "periodic_blade_trailing_edge", periodic=True),
        ],
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=1,
    )
    missing_grid = surface("hub_support_surface", "hub_support")
    missing_grid.pop("uv_grid")

    ledger = build_reconstruction_surface_comparison_ledger(
        {"surfaces": [missing_grid]},
        scope,
    )

    assert ledger["surface_count"] == 1
    assert ledger["status"] == "REJECTED"
    assert ledger["surfaces"][0]["disposition"] == "FAILED_UNRESOLVED"
    assert ledger["surfaces"][0]["reason"] == (
        "reconstruction_surface_uv_grid_missing"
    )


def test_scope_rejects_partition_that_excludes_required_blade_roles():
    scope = build_supported_surface_comparison_scope(
        [
            face("hub", "hub_flowpath_support"),
            face("unsupported", "source_material_boundary", hint="local_boss"),
        ],
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=1,
    )

    assert scope["coverage_complete"] is True
    assert scope["status"] == "REJECTED"
    assert scope["failure_reason"] == "required_comparison_roles_missing"
    assert set(scope["missing_required_roles"]) == {
        "blade_leading_edge",
        "blade_root_attachment",
        "blade_sides",
        "blade_tip",
        "blade_trailing_edge",
    }


def test_scope_rejects_incomplete_periodic_instance_coverage():
    scope = build_supported_surface_comparison_scope(
        [
            face("hub", "hub_flowpath_support"),
            face("blade-1", "periodic_blade_side", periodic=True),
            face("leading-1", "periodic_blade_leading_edge", periodic=True),
            face("root-1", "periodic_blade_root_attachment", periodic=True),
            face("tip-1", "periodic_blade_tip_cap", periodic=True),
            face("trailing-1", "periodic_blade_trailing_edge", periodic=True),
        ],
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=2,
    )

    assert scope["status"] == "REJECTED"
    assert scope["failure_reason"] == "periodic_instance_coverage_incomplete"
    assert scope["periodic_instance_coverage"]["blade_sides"]["observed_count"] == 1


def test_scope_excludes_a_partially_owned_edge_role_from_instance_metrics():
    records = [face("hub", "hub_flowpath_support")]
    for instance_id in ("main-00", "main-01"):
        for role, suffix in (
            ("periodic_blade_side", "side"),
            ("periodic_blade_root_attachment", "root"),
            ("periodic_blade_tip_cap", "tip"),
        ):
            record = face(f"{suffix}-{instance_id}", role, periodic=True)
            record["periodic_instance_id"] = instance_id
            records.append(record)
    partial_leading = face(
        "leading-main-00", "periodic_blade_leading_edge", periodic=True
    )
    partial_leading["periodic_instance_id"] = "main-00"
    records.append(partial_leading)

    scope = build_supported_surface_comparison_scope(
        records,
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=2,
    )

    assert scope["status"] == "PARTIAL_REVIEW"
    assert not any(
        record.get("reconstruction_role") == "blade_leading_edge"
        for record in scope["included_surfaces"]
    )
    excluded = {
        record["source_face_id"]: record["reason"]
        for record in scope["excluded_surfaces"]
    }
    assert excluded["leading-main-00"] == (
        "unresolved_blade_closure_correspondence"
    )


def test_scope_uses_authenticated_population_lattice_indexes():
    records = [face("hub", "hub_flowpath_support")]
    for instance_id in ("main-z", "main-a"):
        for role, suffix in (
            ("periodic_blade_side", "side"),
            ("periodic_blade_root_attachment", "root"),
            ("periodic_blade_tip_cap", "tip"),
            ("periodic_blade_leading_edge", "leading"),
            ("periodic_blade_trailing_edge", "trailing"),
        ):
            record = face(f"{suffix}-{instance_id}", role, periodic=True)
            record["periodic_instance_id"] = instance_id
            records.append(record)

    scope = build_supported_surface_comparison_scope(
        records,
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=2,
        periodic_populations=[
            {
                "classification": "main",
                "count": 2,
                "instances": [
                    {"instance_id": "main-z", "lattice_index": 0},
                    {"instance_id": "main-a", "lattice_index": 1},
                ],
            }
        ],
    )

    assert scope["status"] == "PASS"
    side_indexes = {
        record["periodic_instance_id"]: record[
            "reconstruction_blade_pair_index"
        ]
        for record in scope["included_surfaces"]
        if record.get("reconstruction_role") == "blade_sides"
    }
    assert side_indexes == {"main-z": 0, "main-a": 1}


def test_scope_rejects_instance_membership_that_disagrees_with_populations():
    records = [face("hub", "hub_flowpath_support")]
    for instance_id in ("main-00", "main-01", "main-02", "splitter-00"):
        for role, suffix in (
            ("periodic_blade_side", "side"),
            ("periodic_blade_root_attachment", "root"),
            ("periodic_blade_tip_cap", "tip"),
            ("periodic_blade_leading_edge", "leading"),
            ("periodic_blade_trailing_edge", "trailing"),
        ):
            record = face(f"{suffix}-{instance_id}", role, periodic=True)
            record["periodic_instance_id"] = instance_id
            records.append(record)

    scope = build_supported_surface_comparison_scope(
        records,
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=4,
        periodic_populations=[
            {
                "classification": "main",
                "count": 2,
                "instances": [
                    {"instance_id": "main-00", "lattice_index": 0},
                    {"instance_id": "main-01", "lattice_index": 1},
                ],
            },
            {
                "classification": "splitter",
                "count": 2,
                "instances": [
                    {"instance_id": "splitter-00", "lattice_index": 0},
                    {"instance_id": "splitter-01", "lattice_index": 1},
                ],
            },
        ],
    )

    assert scope["status"] == "REJECTED"
    assert scope["failure_reason"] == "periodic_instance_membership_unresolved"


def test_scope_excludes_partial_edges_only_for_incomplete_population():
    records = [face("hub", "hub_flowpath_support")]
    population_ids = {
        "main": ("main-00", "main-01"),
        "splitter": ("splitter-00", "splitter-01"),
    }
    for instance_ids in population_ids.values():
        for instance_id in instance_ids:
            for role, suffix in (
                ("periodic_blade_side", "side"),
                ("periodic_blade_root_attachment", "root"),
                ("periodic_blade_tip_cap", "tip"),
                ("periodic_blade_trailing_edge", "trailing"),
            ):
                record = face(f"{suffix}-{instance_id}", role, periodic=True)
                record["periodic_instance_id"] = instance_id
                records.append(record)
    for instance_id in ("main-00", "main-01", "splitter-00"):
        record = face(
            f"leading-{instance_id}", "periodic_blade_leading_edge", periodic=True
        )
        record["periodic_instance_id"] = instance_id
        records.append(record)

    scope = build_supported_surface_comparison_scope(
        records,
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=4,
        periodic_populations=[
                {
                    "classification": population,
                    "count": len(instance_ids),
                    "instances": [
                    {"instance_id": instance_id, "lattice_index": index}
                    for index, instance_id in enumerate(instance_ids)
                ],
            }
            for population, instance_ids in population_ids.items()
        ],
    )

    assert scope["status"] == "PARTIAL_REVIEW"
    included_leading = {
        record["periodic_instance_id"]
        for record in scope["included_surfaces"]
        if record.get("reconstruction_role") == "blade_leading_edge"
    }
    assert included_leading == {"main-00", "main-01"}
    excluded_leading = {
        record["periodic_instance_id"]
        for record in scope["excluded_surfaces"]
        if record.get("reason") == "unresolved_blade_closure_correspondence"
        and record.get("semantic_role") == "periodic_blade_leading_edge"
    }
    assert excluded_leading == {"splitter-00"}
    assert scope["periodic_population_coverage"]["blade_leading_edge"]["main"][
        "complete"
    ] is True
    assert scope["periodic_population_coverage"]["blade_leading_edge"][
        "splitter"
    ]["complete"] is False


def test_scope_rejects_invalid_population_count_and_lattice_contracts():
    records = [face("hub", "hub_flowpath_support")]
    for instance_id in ("main-00", "main-01"):
        record = face(f"side-{instance_id}", "periodic_blade_side", periodic=True)
        record["periodic_instance_id"] = instance_id
        records.append(record)

    count_mismatch = build_supported_surface_comparison_scope(
        records,
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=2,
        periodic_populations=[
            {
                "classification": "main",
                "count": 3,
                "instances": [
                    {"instance_id": "main-00", "lattice_index": 0},
                    {"instance_id": "main-01", "lattice_index": 1},
                ],
            }
        ],
    )
    assert count_mismatch["failure_reason"] == (
        "invalid_periodic_population_evidence"
    )

    duplicate_lattice = build_supported_surface_comparison_scope(
        records,
        measurements={},
        topology_mode="open",
        expected_periodic_instance_count=2,
        periodic_populations=[
            {
                "classification": "main",
                "count": 2,
                "instances": [
                    {"instance_id": "main-00", "lattice_index": 0},
                    {"instance_id": "main-01", "lattice_index": 0},
                ],
            }
        ],
    )
    assert duplicate_lattice["failure_reason"] == (
        "invalid_periodic_population_evidence"
    )


def face(
    source_face_id,
    semantic_role,
    *,
    periodic=False,
    hole=False,
    hint="other_material",
):
    return {
        "source_face_id": source_face_id,
        "semantic_role": semantic_role,
        "source_role_hint": hint,
        "periodic_instance_id": "main-01" if periodic else None,
        "periodic_blade_related": periodic,
        "flowpath_adjacent": semantic_role != "source_material_boundary",
        "hole_boundary": hole,
        "geometry_type": "CYLINDER" if hole else "BSPLINE",
    }


def surface(surface_id, role, *, blade_index=None):
    record = {
        "id": surface_id,
        "role": role,
        "material": True,
        "uv_grid": [
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
        ],
    }
    if blade_index is not None:
        record.update(
            {
                "blade_index": blade_index,
                "blade_pair_index": blade_index,
                "blade_class": "main",
            }
        )
    return record
