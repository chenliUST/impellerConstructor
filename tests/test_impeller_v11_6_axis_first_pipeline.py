from __future__ import annotations

# ruff: noqa: E402

import copy
import hashlib
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import cadquery as cq
import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

from part_rule_synthesis import impeller_v11_6_axis_first_pipeline as pipeline
from part_rule_synthesis.impeller_v11_6_v112_mapping import (
    MEASUREMENT_SCHEMA_VERSION,
    V112MappingError,
    V112MappingTolerances,
    map_measurements_to_v112,
    map_measurements_to_v112_review,
)
from step_fixtures import (
    write_axis_first_impeller_step,
    write_axis_first_representable_step,
)
from part_rule_synthesis import impeller_v11_6_step_audit as step_audit


def test_representative_meridional_points_sample_curve_interiors():
    edge = cq.Edge.makeLine(cq.Vector(10.0, 0.0, 0.0), cq.Vector(20.0, 0.0, 10.0))

    class Face:
        def Vertices(self):
            return edge.Vertices()

        def Edges(self):
            return [edge]

    points = pipeline._representative_meridional_points(
        {"faces_by_id": {"blade": Face()}},
        {"source_to_canonical_matrix": np.eye(4).tolist()},
        {"source_face_ids": ["blade"]},
    )

    assert len(points) > 2
    assert any(
        14.0 < radius < 16.0 and 4.0 < z < 6.0 for radius, z in points
    )


def test_exact_incidence_ignores_unreferenced_degenerate_occt_edges():
    shape = cq.Solid.makeCone(10.0, 0.0, 20.0)
    faces_by_id = {
        f"source_face_{index:05d}": face
        for index, face in enumerate(shape.Faces())
    }
    edges_by_id = {
        f"source_edge_{index:05d}": edge
        for index, edge in enumerate(shape.Edges())
    }

    face_edge_ids, edge_face_ids = pipeline._build_exact_incidence_index(
        shape, faces_by_id, edges_by_id
    )

    assert set(face_edge_ids) == set(faces_by_id)
    assert set(edge_face_ids) == set(edges_by_id)
    assert all(face_edge_ids.values())
    assert all(edge_face_ids.values())


def test_open_tip_candidate_prefers_balanced_two_side_contact_length():
    class Edge:
        def __init__(self, length):
            self._length = length

        def Length(self):
            return self._length

    inventory = {
        "face_edge_ids": {
            "side_a": ("small_a", "main_a"),
            "side_b": ("small_b", "main_b"),
            "small_patch": ("small_a", "small_b"),
            "main_cap": ("main_a", "main_b"),
        },
        "edges_by_id": {
            "small_a": Edge(2.95),
            "small_b": Edge(1.72),
            "main_a": Edge(36.52),
            "main_b": Edge(37.48),
        },
    }

    assert pipeline._select_opposite_tip_cap(
        inventory,
        {"small_patch", "main_cap"},
        {"side_a", "side_b"},
    ) == "main_cap"


def test_open_tip_profile_uses_shared_edge_chains_from_both_blade_sides():
    class Edge:
        def __init__(self, length):
            self._length = length

        def Length(self):
            return self._length

    inventory = {
        "face_edge_ids": {
            "pressure": ("pressure_a", "pressure_b", "pressure_root"),
            "suction": ("suction_a", "suction_root"),
            "tip_cap": ("pressure_a", "pressure_b", "suction_a", "cap_outer"),
        },
        "edges_by_id": {
            "pressure_a": Edge(12.0),
            "pressure_b": Edge(8.0),
            "pressure_root": Edge(20.0),
            "suction_a": Edge(21.0),
            "suction_root": Edge(19.0),
            "cap_outer": Edge(3.0),
        },
    }

    groups = pipeline._cap_shared_side_edge_groups(
        inventory,
        "tip_cap",
        {"pressure", "suction"},
    )

    assert groups == [
        ("pressure", ("pressure_a", "pressure_b")),
        ("suction", ("suction_a",)),
    ]


def test_authenticated_blade_side_role_is_not_overwritten_by_hub_adjacency():
    class Face:
        def geomType(self):
            return "BSPLINE"

    instance = {
        "instance_id": "main_instance_0000",
        "source_face_ids": ["side", "root", "closure"],
        "component_completeness": {"blade_side_face_ids": ["side"]},
    }
    inventory = {
        "instance_by_face": {
            "side": "main_instance_0000",
            "root": "main_instance_0000",
            "closure": "main_instance_0000",
        },
        "faces_by_id": {
            "hub": Face(),
            "side": Face(),
            "root": Face(),
            "closure": Face(),
        },
        "records_by_id": {},
        "source_manifest": {
            "adjacency": {
                "hub": ["side", "root"],
                "side": ["hub"],
                "root": ["hub"],
                "closure": [],
            }
        },
    }
    semantics = {
        "periodic_population_recovery": {
            "populations": [{"instances": [instance]}]
        },
        "face_roles": {},
    }
    topology = {
        "mode": "open",
        "hub_face_id": "hub",
        "hub_support_face_ids": ["hub"],
        "open_tip_caps": {},
    }

    assignments = pipeline._semantic_assignments(inventory, semantics, topology)

    assert assignments["side"]["role"] == "periodic_blade_side"
    assert assignments["root"]["role"] == "periodic_blade_root_attachment"


def test_periodic_closure_faces_are_split_by_exact_streamwise_position(monkeypatch):
    class Face:
        def geomType(self):
            return "BSPLINE"

    instance = {
        "instance_id": "main_instance_0000",
        "source_face_ids": [
            "side_a",
            "side_b",
            "root_a",
            "root_b",
            "leading",
            "trailing_a",
            "trailing_b",
            "tip",
        ],
        "component_completeness": {
            "blade_side_face_ids": ["side_a", "side_b"]
        },
    }
    face_ids = ["hub", *instance["source_face_ids"]]
    inventory = {
        "instance_by_face": {
            face_id: "main_instance_0000"
            for face_id in instance["source_face_ids"]
        },
        "faces_by_id": {face_id: Face() for face_id in face_ids},
        "records_by_id": {},
        "source_manifest": {
            "adjacency": {
                "hub": ["root_a", "root_b", "leading"],
                "side_a": [
                    "root_a",
                    "root_b",
                    "leading",
                    "trailing_a",
                    "tip",
                ],
                "side_b": [
                    "root_a",
                    "root_b",
                    "trailing_b",
                    "tip",
                ],
                "root_a": ["hub", "side_a", "side_b"],
                "root_b": ["hub", "side_a", "side_b"],
                "leading": ["hub", "side_a"],
                "trailing_a": ["side_a"],
                "trailing_b": ["side_b"],
                "tip": ["side_a", "side_b"],
            }
        },
    }
    semantics = {
        "periodic_population_recovery": {
            "populations": [{"instances": [instance]}]
        },
        "face_roles": {},
    }
    topology = {
        "mode": "open",
        "hub_face_id": "hub",
        "hub_support_face_ids": ["hub"],
        "open_tip_caps": {"main_instance_0000": "tip"},
    }
    assignments = pipeline._semantic_assignments(inventory, semantics, topology)
    streamwise = {"leading": 1.0, "trailing_a": 9.0, "trailing_b": 10.0}
    monkeypatch.setattr(
        pipeline,
        "_closure_meridional_s",
        lambda _inventory, face_id, _sides, _matrix, _profile: streamwise[
            face_id
        ],
    )

    evidence = pipeline._refine_periodic_closure_assignments(
        assignments,
        inventory,
        semantics,
        topology,
        matrix=[[1.0, 0.0, 0.0, 0.0]] * 4,
        hub_profile_rz_mm=[[1.0, 0.0], [2.0, 1.0]],
    )

    assert assignments["root_a"]["role"] == "periodic_blade_root_attachment"
    assert assignments["root_b"]["role"] == "periodic_blade_root_attachment"
    assert assignments["leading"]["role"] == "periodic_blade_leading_edge"
    assert assignments["trailing_a"]["role"] == "periodic_blade_trailing_edge"
    assert assignments["trailing_b"]["role"] == "periodic_blade_trailing_edge"
    assert evidence["main_instance_0000"]["leading_edge_source_face_ids"] == [
        "leading"
    ]
    assert evidence["main_instance_0000"]["trailing_edge_source_face_ids"] == [
        "trailing_a",
        "trailing_b",
    ]


def test_hub_group_prefers_contact_and_adds_only_missing_same_type_patches():
    all_instances = {f"blade_{index:02d}" for index in range(13)}
    groups = [
        {
            "geometry_type": "CYLINDER",
            "member_face_ids": ["outer_rim"],
            "periodic_instance_ids": set(all_instances),
            "adjacent_periodic_face_ids": {"rim_contacts"},
            "shared_contact_length_mm": 47.0,
            "total_area_mm2": 271.0,
            "mean_area_mm2": 271.0,
        },
        {
            "geometry_type": "BSPLINE",
            "member_face_ids": ["hub_main"],
            "periodic_instance_ids": set(all_instances - {"blade_06"}),
            "adjacent_periodic_face_ids": {"hub_contacts"},
            "shared_contact_length_mm": 1061.0,
            "total_area_mm2": 4600.0,
            "mean_area_mm2": 4600.0,
        },
        {
            "geometry_type": "BSPLINE",
            "member_face_ids": ["hub_gap"],
            "periodic_instance_ids": {"blade_05", "blade_06"},
            "adjacent_periodic_face_ids": {"gap_contacts"},
            "shared_contact_length_mm": 105.0,
            "total_area_mm2": 264.0,
            "mean_area_mm2": 264.0,
        },
    ]

    selected = pipeline._select_complete_hub_group(groups, all_instances)

    assert selected["member_face_ids"] == ["hub_gap", "hub_main"]
    assert selected["periodic_instance_ids"] == all_instances
    assert selected["shared_contact_length_mm"] == pytest.approx(1166.0)


def test_hub_passage_patch_family_does_not_stop_at_adjacency_only_coverage():
    all_instances = {f"main_instance_{index:04d}" for index in range(13)}
    seed_instances = all_instances - {"main_instance_0006"}
    groups = [
        {
            "geometry_type": "BSPLINE",
            "member_face_ids": [f"hub_{index:02d}" for index in range(10)],
            "periodic_instance_ids": set(seed_instances),
            "member_periodic_instance_ids": {
                f"hub_{index:02d}": [
                    f"main_instance_{owner:04d}"
                ]
                for index, owner in enumerate(
                    [0, 1, 2, 3, 4, 5, 7, 8, 9, 10]
                )
            },
            "member_contact_length_mm": {
                f"hub_{index:02d}": 106.19 for index in range(10)
            },
            "member_area_mm2": {
                f"hub_{index:02d}": 464.77 for index in range(10)
            },
            "adjacent_periodic_face_ids": {"seed-contacts"},
            "shared_contact_length_mm": 1061.9,
            "total_area_mm2": 4647.7,
            "mean_area_mm2": 464.77,
        },
        {
            "geometry_type": "BSPLINE",
            "member_face_ids": ["hub_gap"],
            "periodic_instance_ids": {"main_instance_0005", "main_instance_0006"},
            "member_periodic_instance_ids": {
                "hub_gap": ["main_instance_0005", "main_instance_0006"]
            },
            "adjacent_periodic_face_ids": {"gap-contacts"},
            "shared_contact_length_mm": 105.7,
            "total_area_mm2": 264.4,
            "mean_area_mm2": 264.4,
        },
        {
            "geometry_type": "BSPLINE",
            "member_face_ids": ["hub_seam_a"],
            "periodic_instance_ids": {"main_instance_0010", "main_instance_0011"},
            "member_periodic_instance_ids": {
                "hub_seam_a": ["main_instance_0010", "main_instance_0011"]
            },
            "adjacent_periodic_face_ids": {"seam-a-contacts"},
            "shared_contact_length_mm": 100.1,
            "total_area_mm2": 463.6,
            "mean_area_mm2": 463.6,
        },
        {
            "geometry_type": "BSPLINE",
            "member_face_ids": ["hub_seam_b"],
            "periodic_instance_ids": {"main_instance_0000", "main_instance_0012"},
            "member_periodic_instance_ids": {
                "hub_seam_b": ["main_instance_0000", "main_instance_0012"]
            },
            "adjacent_periodic_face_ids": {"seam-b-contacts"},
            "shared_contact_length_mm": 86.5,
            "total_area_mm2": 457.6,
            "mean_area_mm2": 457.6,
        },
        {
            "geometry_type": "BSPLINE",
            "member_face_ids": ["collar"],
            "periodic_instance_ids": set(all_instances),
            "member_periodic_instance_ids": {
                "collar": sorted(all_instances)
            },
            "adjacent_periodic_face_ids": {"collar-contacts"},
            "shared_contact_length_mm": 40.0,
            "total_area_mm2": 160.0,
            "mean_area_mm2": 160.0,
        },
    ]

    selected = pipeline._select_complete_hub_group(groups, all_instances)

    assert len(selected["member_face_ids"]) == 13
    assert {"hub_gap", "hub_seam_a", "hub_seam_b"} <= set(
        selected["member_face_ids"]
    )
    assert "collar" not in selected["member_face_ids"]
    assert selected["periodic_passage_face_coverage"]["complete"] is True
    assert selected["periodic_passage_face_coverage"]["observed_count"] == 13


def test_hub_shared_support_split_into_fewer_faces_is_not_forced_to_pitch_count():
    all_instances = {f"main_instance_{index:04d}" for index in range(13)}
    faces = [f"trimmed_support_{index}" for index in range(7)]
    groups = [
        {
            "geometry_type": "BSPLINE",
            "member_face_ids": faces,
            "periodic_instance_ids": set(all_instances),
            "member_periodic_instance_ids": {
                face_id: sorted(all_instances) for face_id in faces
            },
            "adjacent_periodic_face_ids": {"all-contacts"},
            "shared_contact_length_mm": 700.0,
            "total_area_mm2": 3500.0,
            "mean_area_mm2": 500.0,
        }
    ]

    selected = pipeline._select_complete_hub_group(groups, all_instances)

    assert selected["member_face_ids"] == faces
    assert selected["periodic_passage_face_coverage"]["mode"] == (
        "shared_support_patch"
    )
    assert selected["periodic_passage_face_coverage"]["complete"] is True


def test_hub_singleton_area_groups_still_require_one_passage_face_per_pitch():
    all_instances = {f"main_instance_{index:04d}" for index in range(13)}
    groups = []
    for index in range(13):
        face_id = f"hub_passage_{index:02d}"
        groups.append(
            {
                "geometry_type": "BSPLINE",
                "member_face_ids": [face_id],
                "periodic_instance_ids": {
                    f"main_instance_{index:04d}",
                    f"main_instance_{(index + 1) % 13:04d}",
                },
                "member_periodic_instance_ids": {
                    face_id: [
                        f"main_instance_{index:04d}",
                        f"main_instance_{(index + 1) % 13:04d}",
                    ]
                },
                "member_contact_length_mm": {face_id: 80.0 + index},
                "member_area_mm2": {face_id: 450.0 + index},
                "adjacent_periodic_face_ids": {f"contact_{index:02d}"},
                "shared_contact_length_mm": 80.0 + index,
                "total_area_mm2": 450.0 + index,
                "mean_area_mm2": 450.0 + index,
            }
        )

    selected = pipeline._select_complete_hub_group(groups, all_instances)

    assert len(selected["member_face_ids"]) == 13
    assert selected["periodic_passage_face_coverage"] == {
        "mode": "periodic_passage_patches",
        "ownership_authority": "one_face_per_periodic_instance_bipartite_match",
        "expected_count": 13,
        "observed_count": 13,
        "instance_to_face_id": selected["periodic_passage_face_coverage"][
            "instance_to_face_id"
        ],
        "complete": True,
    }


def _source_inputs(tmp_path: Path, **fixture_options):
    source_path = write_axis_first_impeller_step(
        tmp_path / "axis-first.step", **fixture_options
    )
    shape, source = step_audit.load_step_source(source_path)
    frame = step_audit.resolve_canonical_frame(shape, source)
    semantics = step_audit.classify_impeller_semantics(shape, source, frame)
    return shape, source, frame, semantics


def test_support_classifier_uses_authenticated_adjacency_for_open_and_closed_sources(tmp_path):
    for closed_shroud, expected_mode in ((False, "open"), (True, "closed")):
        case_dir = tmp_path / expected_mode
        case_dir.mkdir()
        shape, source, frame, semantics = _source_inputs(
            case_dir, blade_count=8, closed_shroud=closed_shroud
        )
        inventory = pipeline._source_inventory(shape, source, frame, semantics)
        assert all(
            face_id in inventory["edge_face_ids"][edge_id]
            for face_id, edge_ids in inventory["face_edge_ids"].items()
            for edge_id in edge_ids
        )
        assert all(
            edge_id in inventory["face_edge_ids"][face_id]
            for edge_id, face_ids in inventory["edge_face_ids"].items()
            for face_id in face_ids
        )
        topology = pipeline._classify_support_topology(inventory, frame, semantics)

        assert topology["mode"] == expected_mode
        assert topology["classification_authority"] == (
            "authenticated_nonperiodic_periodic_adjacency_contact_length_groups"
        )
        assert topology["support_candidates"]
        assert topology["hub_face_id"] not in inventory["instance_by_face"]
        if closed_shroud:
            assert topology["inner_shroud_face_id"] != topology["hub_face_id"]
            assert topology["outer_shroud_face_id"] not in inventory["instance_by_face"]
    assert "_edge_owned_by_face" not in inspect.getsource(pipeline)


def test_closed_shroud_zero_chamfer_requires_direct_sharp_boundary_proof(tmp_path):
    shape, source, frame, semantics = _source_inputs(
        tmp_path, blade_count=8, closed_shroud=True
    )
    inventory = pipeline._source_inventory(shape, source, frame, semantics)
    topology = pipeline._classify_support_topology(
        inventory, frame, semantics
    )

    material = pipeline._measure_closed_shroud_material(
        inventory,
        frame,
        topology,
        support={},
        tolerance_mm=pipeline._source_tolerance(frame),
    )

    evidence = material["hood_chamfer_radius_mm"]["evidence"]
    assert evidence["absence_proven"] is True
    assert len(evidence["boundary_source_face_ids"]) == 2
    assert len(evidence["direct_sharp_source_edge_ids"]) >= 4
    assert set(evidence["boundary_source_face_ids"]).issubset(
        material["hood_chamfer_radius_mm"]["source_ids"]
    )


def test_closed_shroud_support_mapping_is_module_authenticated(tmp_path):
    shape, source, frame, semantics = _source_inputs(
        tmp_path, blade_count=8, closed_shroud=True
    )
    inventory = pipeline._source_inventory(shape, source, frame, semantics)

    support = pipeline._recover_support_evidence(
        inventory, frame, semantics
    )

    assert support["topology_mode"] == "closed"
    assert support["topology"]["status"] == "PASS"
    assert support["topology"]["decision"] == "closed"
    assert support["tip_reference_or_shroud"]["material"] is True
    assert support["hub_profile"]["provenance"]["projection_method"] == (
        "source_order_monotone_meridional_trace_validation"
    )
    assert support["mapping_fits"]["hub"]["fit_status"] == "PASS"
    assert support["mapping_fits"]["tip_or_shroud"]["fit_status"] == "PASS"


@pytest.mark.parametrize("closed_shroud", [False, True])
def test_task9_mapping_retains_full_periodic_and_material_partitions(
    tmp_path, closed_shroud
):
    shape, source, frame, semantics = _source_inputs(
        tmp_path, blade_count=8, closed_shroud=closed_shroud
    )
    inventory = pipeline._source_inventory(shape, source, frame, semantics)
    support = pipeline._recover_support_evidence(
        inventory, frame, semantics
    )
    periodic = pipeline._recover_periodic_evidence(
        inventory, frame, semantics, support=support
    )

    recovered = periodic["pattern_population_evidence"]
    assert recovered["main_blade_count"] == 8
    assert len(recovered["main"]["instances"]) == 8
    assert all(
        instance["transform_from_representative"]
        for instance in recovered["main"]["instances"]
    )
    assert periodic["measurement_tolerance_mm"] >= max(
        instance["residual_to_representative_mm"]
        for instance in recovered["main"]["instances"]
    )
    assert periodic["source_linear_tolerance_mm"] <= periodic[
        "measurement_tolerance_mm"
    ]
    assert periodic["main"]["streamwise_interval_evidence"]["method"] == (
        "nearest_projection_to_corresponded_hub_tip_support_strip"
    )
    assert 0.0 <= periodic["main"]["streamwise_interval_s"][0]
    assert periodic["main"]["streamwise_interval_s"][1] <= 1.0
    material = support["pattern_material_partition"]
    assert material["mode"] == ("closed" if closed_shroud else "open")
    assert sorted(material["hub_attachment_face_ids_by_instance"]) == sorted(
        instance["instance_id"] for instance in recovered["main"]["instances"]
    )
    if closed_shroud:
        assert material["open_tip_reference_face_ids"] is None
        assert material["material_shroud"]["finite_thickness"][
            "finite_positive"
        ] is True
    else:
        assert material["material_shroud"] is None
        assert len(material["open_tip_reference_face_ids"]) == 8


def test_attachment_recovery_retains_every_source_patch_touching_support():
    inventory = {
        "source_manifest": {
            "adjacency": {
                "root-a": ["hub"],
                "root-b": ["hub"],
                "blade-side": ["root-a"],
            }
        },
        "records_by_id": {
            "root-a": {"area_mm2": 4.0},
            "root-b": {"area_mm2": 2.0},
            "blade-side": {"area_mm2": 20.0},
        },
    }
    instances = [
        {
            "instance_id": "main-0",
            "source_face_ids": ["root-a", "root-b", "blade-side"],
        }
    ]

    recovered = pipeline._attachment_faces_by_instance(
        inventory, instances, ["hub"]
    )

    assert recovered == {"main-0": ["root-a", "root-b"]}


def test_periodic_representative_fit_has_independent_review_grade_ceiling():
    frame = {
        "outer_radius_mm": 50.0,
        "axis_consensus": {
            "selected_cluster": {"tolerance": {"line_distance_mm": 0.02}}
        },
    }

    with pytest.raises(pipeline.AxisFirstPipelineError) as raised:
        pipeline._bounded_representative_fit_tolerance(frame, 5.0)

    assert raised.value.reason == "v116_periodic_population_ambiguous"


def test_measurement_sector_adds_one_pitch_around_swept_blade_envelope():
    sector, evidence = pipeline._measurement_sector_from_envelope(
        {"start_angle_deg": 244.0, "end_angle_deg": 286.0, "span_deg": 42.0},
        pitch_deg=27.5,
    )

    assert sector == pytest.approx((216.5, 313.5))
    assert evidence == {
        "method": "representative_side_envelope_plus_one_pitch_each_side",
        "raw_envelope_deg": [244.0, 286.0],
        "raw_span_deg": 42.0,
        "margin_each_side_deg": 27.5,
        "measurement_span_deg": 97.0,
    }


def test_section_stage_drives_adaptation_from_revolved_exact_section_metrics(monkeypatch):
    calls = []
    instance = {
        "source_face_ids": ["side-a", "side-b", "leading", "trailing"],
        "angular_envelope_deg": {"center_angle_deg": 0.0},
        "component_completeness": {
            "blade_side_face_ids": ["side-a", "side-b"],
        },
    }
    loop = SimpleNamespace(
        source_face_ids=("side-a", "side-b"),
        source_edge_ids=("edge-a", "edge-b"),
        closure_gap_mm=0.0,
        self_intersection_count=0,
    )
    result = SimpleNamespace(accepted_loop=loop, as_dict=lambda: {"exact": True})
    profile = SimpleNamespace(points_rz_mm=((10.0, 0.0), (10.0, 5.0)))
    correspondence = SimpleNamespace()
    lattice = SimpleNamespace(
        stations=(
            SimpleNamespace(h=0.1, metrics={"mean_thickness_mm": 1.0}),
            SimpleNamespace(h=0.9, metrics={"mean_thickness_mm": 1.2}),
        ),
        as_dict=lambda: {"station_count": 2},
    )
    inventory = {
        "shape": object(),
        "faces_by_id": {
            **{face_id: object() for face_id in instance["source_face_ids"]},
            "non-representative-face": object(),
        },
        "records_by_id": {
            "side-a": {"centroid_mm": [10.0, 0.0, 0.0]},
            "side-b": {"centroid_mm": [10.0, 0.0, 0.0]},
            "leading": {"centroid_mm": [9.0, 0.0, 0.0]},
            "trailing": {"centroid_mm": [11.0, 0.0, 0.0]},
        },
        "edges_by_id": {},
    }
    frame = {"source_to_canonical_matrix": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}
    support = {
        "mapping_fits": {
            "hub": {"control_points_rz_mm": [[1, 0]] * 6},
            "tip_or_shroud": {"control_points_rz_mm": [[2, 1]] * 6},
        },
        "support_face_ids": {"mode": "open"},
    }
    population = {"representative_instance": instance, "angular_sector_deg": (-5.0, 5.0)}

    monkeypatch.setattr(pipeline, "_source_tolerance", lambda _frame: 0.01)
    monkeypatch.setattr(
        pipeline, "_representative_face_roles", lambda *_args, **_kwargs: {}
    )
    monkeypatch.setattr(
        pipeline,
        "_active_span_evidence_from_adjacency",
        lambda *_args: ({"source_edge_ids": ["root"]}, {"source_edge_ids": ["tip"]}),
    )
    monkeypatch.setattr(
        pipeline,
        "_measured_active_span_interval",
        lambda *_args, **_kwargs: (
            0.1,
            0.9,
            {
                "active_root_h": 0.1,
                "active_tip_h": 0.9,
                "minimum_support_separation_mm": 1.0,
                "active_span_mm": 0.8,
                "minimum_measurable_active_span_mm": 0.08,
                "local_thickness_proxy_mm": 0.32,
                "source_tolerance_mm": 0.01,
                "measurement_authority": "attachment_clearance_on_authenticated_meridional_supports",
                "source_ids": ["root", "tip"],
            },
        ),
    )
    monkeypatch.setattr(pipeline.section_recovery, "solve_meridional_correspondence", lambda *_args: correspondence)
    monkeypatch.setattr(pipeline.section_recovery, "build_ordered_span_profiles", lambda *_args: (profile, profile, profile))
    monkeypatch.setattr(pipeline.section_recovery, "make_occt_revolved_measurement_surface", lambda *_args, **_kwargs: "revolved")
    monkeypatch.setattr(pipeline, "_measurement_surface_in_source_frame", lambda surface, *_args: surface)
    monkeypatch.setattr(pipeline, "_meridional_unwrapped_projector", lambda *_args: (lambda _point: (0.0, 0.0), (0.0, 0.0, 1.0)))
    monkeypatch.setattr(
        pipeline,
        "_decompose_measured_section_loop",
        lambda *_args: "decomposition",
    )
    monkeypatch.setattr(
        pipeline,
        "_measure_section_thickness",
        lambda *_args, **_kwargs: SimpleNamespace(
            minimum_mm=0.8, maximum_mm=1.2, mean_mm=1.0
        ),
    )
    monkeypatch.setattr(pipeline, "_preliminary_section_metrics", lambda *_args: {"mean_thickness_mm": 1.1, "camber_turn_deg": 2.0, "edge_curvature_per_mm": 0.1})
    monkeypatch.setattr(
        pipeline, "_assert_section_segment_fit_quality", lambda *_args: None
    )
    monkeypatch.setattr(
        pipeline,
        "_station_for_mapping",
        lambda h, *_args, **_kwargs: {"h": h, "source_ids": ["side-a"]},
    )
    monkeypatch.setattr(pipeline, "_decomposition_summary", lambda _value: {"segments": {}})
    def section_probe(source_shape, surface, **kwargs):
        assert source_shape is inventory["shape"]
        assert set(kwargs["source_faces_by_id"]) == set(inventory["faces_by_id"])
        assert set(kwargs["allowed_source_face_ids"]) == set(instance["source_face_ids"])
        assert kwargs["source_shape_scope"] == "complete_source_shape"
        assert kwargs["edge_sample_count"] == 129
        assert kwargs["angular_sector_deg"] == population["angular_sector_deg"]
        assert np.array_equal(
            kwargs["angular_source_to_canonical_matrix"],
            np.asarray(frame["source_to_canonical_matrix"]),
        )
        calls.append(surface)
        return result

    monkeypatch.setattr(
        pipeline.section_recovery, "section_source_solid", section_probe
    )

    def adaptive_probe(_hub, _tip, sampler, **_kwargs):
        assert sampler(0.1)["mean_thickness_mm"] == 1.1
        assert sampler(0.5)["camber_turn_deg"] == 2.0
        return lattice

    monkeypatch.setattr(pipeline.section_recovery, "build_adaptive_span_profiles", adaptive_probe)
    attachments = {
        "root": SimpleNamespace(
            lift_mm=1.0,
            retained_source_edge_ids=("root",),
        )
    }
    family, records = pipeline._section_family(
        inventory, frame, support, "main", population, attachments
    )

    assert calls and set(calls) == {"revolved"}
    assert [station["h"] for station in family["stations"]] == [0.0, 1.0]
    assert all(record["exact_section"] == {"exact": True} for record in records)
    assert "gp_Pln" not in inspect.getsource(pipeline._section_family)


def test_unknown_material_features_fail_closed_without_bbox_or_zero_measurements(tmp_path):
    shape, source, frame, semantics = _source_inputs(tmp_path, blade_count=8)
    inventory = pipeline._source_inventory(shape, source, frame, semantics)

    with pytest.raises(pipeline.AxisFirstPipelineError) as caught:
        pipeline._material_measurements(
            inventory,
            frame,
            {"mode": "open", "hub_face_id": "source_face_00002"},
            {},
            {},
        )

    assert caught.value.reason == "v116_v112_mapping_residual_exceeded"
    evidence = caught.value.details["failure_evidence"]
    assert evidence["forbidden_authorities"] == [
        "bounding_box_extent",
        "preset_default",
        "implicit_zero",
    ]


def test_mounting_bore_uses_axis_consensus_family_not_smaller_spline_root():
    records = [
        {
            "face_id": "spline-root-a",
            "face_ids": ["spline-root-a"],
            "radius_mm": 4.2,
            "axis_residual_mm": 0.0,
            "axis_alignment": 1.0,
            "analytic_area_mm2": 10.0,
            "circular_source_edge_ids": ["edge-a"],
            "source_ids": ["spline-root-a", "edge-a"],
        },
        {
            "face_id": "spline-root-b",
            "face_ids": ["spline-root-b"],
            "radius_mm": 4.2,
            "axis_residual_mm": 0.0,
            "axis_alignment": 1.0,
            "analytic_area_mm2": 11.0,
            "circular_source_edge_ids": ["edge-b"],
            "source_ids": ["spline-root-b", "edge-b"],
        },
        {
            "face_id": "nominal-bore",
            "face_ids": ["nominal-bore"],
            "radius_mm": 7.9,
            "axis_residual_mm": 0.0,
            "axis_alignment": 1.0,
            "analytic_area_mm2": 100.0,
            "circular_source_edge_ids": ["edge-c", "edge-d"],
            "source_ids": ["nominal-bore", "edge-c", "edge-d"],
        },
    ]

    groups = pipeline._group_coaxial_cylinder_records(records, 0.03)
    selected = pipeline._select_mounting_bore_group(
        groups, {"main_bore_radius_mm": 7.9}, 0.03
    )

    assert [group["radius_mm"] for group in groups] == [4.2, 7.9]
    assert groups[0]["face_ids"] == ["spline-root-a", "spline-root-b"]
    assert selected["face_ids"] == ["nominal-bore"]


def test_source_sha_is_provenance_only_for_mapping_input(monkeypatch):
    base = {
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
        "provenance": {"source_sha256": "0" * 64},
        "support_fits": {},
    }
    result = pipeline.MeasurementBundleResult(
        measurements=base,
        support_evidence={},
        periodic_evidence={},
        section_evidence={"section_loop_records": []},
        stage_evidence=(),
    )
    captured = []

    def map_probe(measurements, *, tolerances, initial_guess=None):
        captured.append(copy.deepcopy(measurements))
        canonical = copy.deepcopy(measurements)
        canonical["provenance"]["source_sha256"] = "0" * 64
        return {
            "parameters": {"blade_count": 8},
            "mapping_status": "PASS",
            "constructor_input_hash_sha256": pipeline.stable_measurement_hash(canonical),
            "provenance": {"canonical_hash_excludes_source_identity": True},
        }

    def bundle_probe(_shape, source_manifest, _frame, _semantics):
        result.measurements["provenance"]["source_sha256"] = source_manifest["sha256"]
        return result

    monkeypatch.setattr(pipeline, "build_measurement_bundle", bundle_probe)
    monkeypatch.setattr(pipeline, "map_measurements_to_v112", map_probe)

    first = pipeline.extract_v11_parameters(None, {"sha256": "1" * 64}, {}, {})
    second = pipeline.extract_v11_parameters(None, {"sha256": "2" * 64}, {}, {})

    assert captured[0]["provenance"]["source_sha256"] == "1" * 64
    assert captured[1]["provenance"]["source_sha256"] == "2" * 64
    assert first["constructor_input_hash_sha256"] == second["constructor_input_hash_sha256"]
    assert first["unsupported_source_feature_audit"]["complete"] is False
    assert first["comparison_scope"]["status"] == "REJECTED"
    assert first["comparison_scope"]["failure_reason"] == "empty_source_face_inventory"


def test_review_extraction_preserves_measurement_and_task8_authority(monkeypatch):
    measurements = {
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
        "provenance": {"source_sha256": "a" * 64},
        "support_fits": {},
        "topology": {"material_measurements": {}},
        "populations": {"main": {"count": 8}, "splitter": None, "source_ids": []},
    }
    result = pipeline.MeasurementBundleResult(
        measurements=measurements,
        support_evidence={"status": "PASS", "support_face_ids": {"hub": ["hub"]}},
        periodic_evidence={"status": "PASS", "main": {"count": 8}},
        section_evidence={"section_loop_records": []},
        stage_evidence=(),
    )

    monkeypatch.setattr(pipeline, "build_measurement_bundle", lambda *_args: result)
    monkeypatch.setattr(
        pipeline,
        "map_measurements_to_v112_review",
        lambda *_args, **_kwargs: {
            "parameters": {"blade_count": 8},
            "mapping_status": "REJECTED_REVIEW_CANDIDATE",
            "promotable": False,
            "constructor_input_hash_sha256": "b" * 64,
            "objective_terms": {"camber": {"gate": {"status": "FAIL"}}},
        },
    )

    mapped = pipeline.extract_v11_review_parameters(
        None, {"sha256": "a" * 64}, {}, {}
    )

    assert mapped["mapping_status"] == "REJECTED_REVIEW_CANDIDATE"
    assert mapped["measurement_bundle"] == measurements
    assert mapped["support_recovery"]["status"] == "PASS"
    assert mapped["periodic_provenance"]["main"]["count"] == 8
    assert mapped["task8_reconstruction_evidence_hash_sha256"] == (
        pipeline.task8_reconstruction_evidence_hash(
            mapped["support_recovery"], mapped["periodic_provenance"], "a" * 64
        )
    )


@pytest.mark.parametrize(
    "reason",
    [
        "v116_v112_measurement_schema_invalid",
        "v116_v112_mapping_solver_exception",
        "v116_v112_material_domain_failed",
        "v116_v112_topology_failed",
    ],
)
def test_mapping_wrapper_preserves_non_residual_failure_reason(reason):
    result = pipeline.MeasurementBundleResult(
        measurements={},
        support_evidence={},
        periodic_evidence={},
        section_evidence={},
        stage_evidence=(),
    )

    with pytest.raises(pipeline.AxisFirstPipelineError) as exc_info:
        pipeline._raise_mapping_error(V112MappingError(reason, "failure"), result)

    assert exc_info.value.reason == reason
    assert exc_info.value.details["failure_evidence"]["upstream_reason"] == reason


def test_unsupported_source_features_come_from_exact_section_evidence():
    audit = pipeline._unsupported_source_feature_audit(
        {
            "section_loop_records": [
                {
                    "population": "main",
                    "support_span_h": 0.5,
                    "exact_section": {
                        "additional_loops": [
                            {
                                "loop_id": "source-hole-loop",
                                "source_face_ids": ["blade-face"],
                                "source_edge_ids": ["hole-edge"],
                            }
                        ],
                        "rejected_edges": [
                            {"reason": "source_face_provenance_not_allowed"},
                            {"reason": "source_face_provenance_not_allowed"},
                        ],
                    },
                }
            ]
        },
        {"provenance": {"source_entity_ids": ["blade-face", "hub-face"]}},
    )

    assert audit["complete"] is False
    assert audit["status"] == "DETECTED_PENDING_REGIONAL_DEVIATION"
    assert audit["features"][0]["feature_id"] == "source-hole-loop"
    assert audit["rejected_section_edge_counts_by_reason"] == {
        "source_face_provenance_not_allowed": 2
    }


def test_authenticated_support_fit_failure_cannot_be_relabelled_as_promotable(monkeypatch):
    evidence = {
        "paths_rz_mm": [
            [[10.0 + index, float(index)] for index in range(6)]
        ],
        "source_tolerance_mm": 0.01,
        "classified_material_domain_rz_mm": [[10.0, 15.0], [0.0, 5.0]],
        "source_face_id": "hub-face",
        "source_face_shape_identity": "hub-shape",
        "source_solid_shape_identity": "solid-shape",
        "semantic_partition_digest": "a" * 64,
        "source_to_canonical_transform": np.eye(4).tolist(),
        "material_uv_domain_validation": {"status": "PASS"},
    }
    calls = 0

    def fail_then_fabricate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise pipeline.support_recovery.SupportRecoveryError(
                "v116_hub_profile_fit_failed", "forced authenticated fit failure"
            )
        return {
            "control_points_rz_mm": [[10.0 + index, float(index)] for index in range(6)],
            "residuals": {"orthogonal_rms_mm": 0.0},
            "pipeline_authenticated_occt_support": {"source_face_ids": ["hub-face"]},
        }

    monkeypatch.setattr(
        pipeline.support_recovery, "fit_hub_profile", fail_then_fabricate
    )

    with pytest.raises(pipeline.AxisFirstPipelineError) as caught:
        pipeline._fit_authenticated_support(
            evidence,
            outer_diameter_mm=100.0,
            semantic_role="hub_profile",
        )

    assert caught.value.reason == "v116_hub_profile_fit_failed"
    assert calls == 1


def test_plain_support_mapping_cannot_fabricate_authenticated_pass():
    fabricated = {
        "control_points_rz_mm": [[10.0 + index, float(index)] for index in range(6)],
        "residuals": {"orthogonal_rms_mm": 0.0},
        "pipeline_authenticated_occt_support": {"source_face_ids": ["hub-face"]},
    }

    with pytest.raises(ValueError, match="module-authenticated"):
        pipeline._serialize_support_record(fabricated)


def test_parameter_rows_distinguish_direct_measurements_from_fitted_parameters():
    parameters = {
        "blade_count": 8,
        "mounting_bore_radius_mm": 7.9,
        "blade_wrap_deg": 42.0,
        "blade_thickness_mm": 3.5,
    }
    objective_terms = {
        "periodicity": {"residual": {"count_difference": 0}, "gate": {"status": "PASS"}},
        "pose": {"residual": {"rms": 0.25}, "gate": {"status": "PASS"}},
        "normal_thickness": {"residual": {"rms": 0.08}, "gate": {"status": "PASS"}},
    }
    measurements = {
        "topology": {
            "material_measurements": {
                "mounting_bore_radius_mm": {
                    "value": 7.9,
                    "unit": "mm",
                    "source_ids": ["bore-face"],
                    "measurement_authority": "occt_exact_brep_feature_measurement",
                }
            }
        },
        "populations": {
            "main": {"count": 8},
            "splitter": None,
            "source_ids": ["blade-population"],
        },
    }

    rows = {
        row["feature_id"].removeprefix("parameter_values."): row
        for row in pipeline._parameter_rows_from_mapping(
            parameters, objective_terms, measurements
        )
    }

    assert rows["blade_count"]["source_measurement"] == 8
    assert rows["mounting_bore_radius_mm"]["source_measurement"] == 7.9
    assert rows["mounting_bore_radius_mm"]["measurement_confidence"] == 1.0
    assert rows["blade_wrap_deg"]["source_measurement"] is None
    assert rows["blade_wrap_deg"]["measurement_confidence"] is None
    assert rows["blade_wrap_deg"]["basis"] == (
        "bounded_v112_mapping_from_authenticated_occt_evidence"
    )
    assert rows["blade_wrap_deg"]["reconstruction_residual"] == {"rms": 0.25}


def test_completed_stage_evidence_contains_source_facts(tmp_path, monkeypatch):
    shape, source, frame, semantics = _source_inputs(tmp_path, blade_count=8)

    def fail_support(*_args):
        raise pipeline.AxisFirstPipelineError(
            "v116_hub_support_classification_failed",
            "forced support failure",
            stage="support_recovery",
            evidence={"source_face_id": "source_face_00002"},
        )

    monkeypatch.setattr(pipeline, "_recover_support_evidence", fail_support)
    with pytest.raises(pipeline.AxisFirstPipelineError) as caught:
        pipeline.build_measurement_bundle(shape, source, frame, semantics)

    completed = caught.value.details["completed_stages"]
    assert completed[0]["stage"] == "source_inventory"
    assert completed[0]["facts"]["source_sha256"] == source["sha256"]
    assert completed[0]["facts"]["face_count"] == len(source["faces"])
    assert completed[0]["evidence_hash_sha256"]


def test_tip_cap_selection_ignores_adversarial_face_centroids(tmp_path):
    path = write_axis_first_representable_step(tmp_path / "topology.step")
    shape, source = step_audit.load_step_source(path)
    frame = step_audit.resolve_canonical_frame(shape, source)
    semantics = step_audit.classify_impeller_semantics(shape, source, frame)
    inventory = pipeline._source_inventory(shape, source, frame, semantics)

    baseline = pipeline._classify_support_topology(inventory, frame, semantics)
    for index, record in enumerate(inventory["records_by_id"].values()):
        record["centroid_mm"] = [1.0e6 - index, -1.0e6 + index, (-1) ** index * 1.0e6]
    adversarial = pipeline._classify_support_topology(inventory, frame, semantics)

    assert adversarial["open_tip_caps"] == baseline["open_tip_caps"]
    assert "centroid" not in inspect.getsource(pipeline._tip_cap_face_ids)


def test_open_tip_active_span_clearance_scales_with_measured_blade_width():
    attachment = SimpleNamespace(
        lift_mm=0.5,
        lift_samples_mm=(0.5,),
        attachment_width_mm=4.0,
    )

    root_h, tip_h, _contract = pipeline._measured_active_span_interval(
        [(10.0, 0.0), (10.0, 10.0)],
        [(20.0, 0.0), (20.0, 10.0)],
        0.02,
        {"source_edge_ids": ["root"]},
        {"source_edge_ids": ["tip"]},
        root_attachment=attachment,
        tip_attachment=None,
    )

    assert root_h == pytest.approx(0.09)
    assert tip_h == pytest.approx(0.96)


def test_active_span_accepts_large_root_lift_when_ordered_body_span_remains():
    attachment = SimpleNamespace(
        lift_mm=3.0,
        lift_samples_mm=(3.0,),
        attachment_width_mm=4.0,
    )

    root_h, tip_h, contract = pipeline._measured_active_span_interval(
        [(10.0, 0.0), (10.0, 10.0)],
        [(20.0, 0.0), (20.0, 10.0)],
        0.02,
        {"source_edge_ids": ["root"]},
        {"source_edge_ids": ["tip"]},
        root_attachment=attachment,
        tip_attachment=None,
    )

    assert root_h == pytest.approx(0.34)
    assert tip_h == pytest.approx(0.96)
    assert contract["active_span_mm"] == pytest.approx(6.2)
    assert contract["minimum_measurable_active_span_mm"] == pytest.approx(0.75)


def test_active_span_rejects_near_collapsed_body_even_when_bounds_remain_ordered():
    attachment = SimpleNamespace(
        lift_mm=4.4,
        lift_samples_mm=(4.4,),
        attachment_width_mm=4.0,
    )

    with pytest.raises(pipeline.AxisFirstPipelineError) as exc_info:
        pipeline._measured_active_span_interval(
            [(10.0, 0.0), (10.0, 10.0)],
            [(20.0, 0.0), (20.0, 10.0)],
            0.02,
            {"source_edge_ids": ["root"]},
            {"source_edge_ids": ["tip"]},
            root_attachment=attachment,
            tip_attachment=attachment,
        )

    assert exc_info.value.reason == "v116_span_surface_ordering_failed"
    evidence = exc_info.value.details["failure_evidence"]
    assert evidence["active_span_mm"] < evidence[
        "minimum_measurable_active_span_mm"
    ]


def test_support_bound_material_planes_ignore_connected_bolt_hole_end_faces(monkeypatch):
    inventory = {
        "faces_by_id": {
            "hub_support": object(),
            "hub_top": object(),
            "hub_bottom": object(),
            "bolt_hole_end": object(),
        },
        "instance_by_face": {},
        "source_manifest": {
            "adjacency": {
                "hub_support": ["hub_top"],
                "hub_top": ["hub_support", "hub_bottom", "bolt_hole_end"],
                "hub_bottom": ["hub_top"],
                "bolt_hole_end": ["hub_top"],
            }
        },
    }
    planes = [
        {"face_id": "hub_top", "axis_parameter_mm": 11.0, "minimum_radius_mm": 8.0, "maximum_radius_mm": 14.0, "centroid_axis_offset_mm": 0.0},
        {"face_id": "bolt_hole_end", "axis_parameter_mm": 12.0, "minimum_radius_mm": 8.0, "maximum_radius_mm": 14.0, "centroid_axis_offset_mm": 20.0},
        {"face_id": "hub_bottom", "axis_parameter_mm": 13.0, "minimum_radius_mm": 8.0, "maximum_radius_mm": 14.0, "centroid_axis_offset_mm": 0.0},
    ]
    monkeypatch.setattr(
        pipeline, "_axis_perpendicular_material_planes", lambda *_args: planes
    )
    support = {
        "mapping_fits": {
            "hub": {
                "control_points_rz_mm": [
                    [10.0, 10.0],
                    [10.5, 8.0],
                    [11.0, 6.0],
                    [12.0, 4.0],
                    [13.0, 2.0],
                    [14.0, 0.0],
                ],
                "source_ids": ["hub_support"],
            }
        }
    }

    wall, bottom, top, evidence = pipeline._measure_support_bound_hub_material(
        inventory,
        {},
        {"radius_mm": 8.0, "source_ids": ["bore"]},
        support,
        (np.zeros(3), np.asarray([0.0, 0.0, 1.0])),
        0.01,
    )

    assert (wall, bottom, top) == pytest.approx((2.0, 2.0, 1.0))
    assert evidence["top_material_plane"]["face_id"] == "hub_top"
    assert evidence["bottom_material_plane"]["face_id"] == "hub_bottom"
    assert "bolt_hole_end" not in {
        evidence["top_material_plane"]["face_id"],
        evidence["bottom_material_plane"]["face_id"],
    }


def test_measured_section_fit_stops_at_first_passing_low_complexity_budget(monkeypatch):
    calls = []

    def fake_decompose(_loop, *, maximum_control_count):
        calls.append(maximum_control_count)
        residual = 0.04 if maximum_control_count == 25 else 0.02
        return SimpleNamespace(
            control_budget=maximum_control_count,
            segments=(SimpleNamespace(fit=SimpleNamespace(residual_max_mm=residual)),),
        )

    monkeypatch.setattr(
        pipeline.section_recovery,
        "decompose_section_loop",
        fake_decompose,
    )

    result = pipeline._decompose_measured_section_loop(object(), 0.03)

    assert calls == [25, 49]
    assert result.control_budget == 49


def test_meridional_projector_preserves_edge_bulge_beyond_profile_endpoints():
    project, _normal = pipeline._meridional_unwrapped_projector(
        [(10.0, 0.0), (20.0, 0.0)],
        np.eye(4),
        0.0,
    )

    assert project((9.0, 0.0, 0.0))[0] == pytest.approx(-1.0)
    assert project((21.0, 0.0, 0.0))[0] == pytest.approx(11.0)


def test_attachment_chain_distinguishes_connectors_from_opposite_retained_loop():
    class Vertex:
        def __init__(self, coordinates):
            self._coordinates = coordinates

        def toTuple(self):
            return self._coordinates

    class Edge:
        def __init__(self, first, second):
            self._vertices = (Vertex(first), Vertex(second))

        def Vertices(self):
            return self._vertices

    footprint_vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    retained_vertices = [(0.1, 0.1, 1.0), (0.9, 0.1, 1.0), (0.9, 0.9, 1.0), (0.1, 0.9, 1.0)]
    edges = {}
    face_edges = {"support": []}
    edge_faces = {}
    for index in range(4):
        next_index = (index + 1) % 4
        footprint_id = f"footprint_{index}"
        connector_id = f"connector_{index}"
        retained_id = f"retained_{index}"
        attachment_id = f"attachment_{index}"
        body_id = f"body_{index}"
        edges[footprint_id] = Edge(footprint_vertices[index], footprint_vertices[next_index])
        edges[connector_id] = Edge(footprint_vertices[index], retained_vertices[index])
        edges[retained_id] = Edge(retained_vertices[index], retained_vertices[next_index])
        face_edges["support"].append(footprint_id)
        face_edges[attachment_id] = [footprint_id, connector_id, retained_id, f"connector_{next_index}"]
        edge_faces[footprint_id] = ["support", attachment_id]
        edge_faces[retained_id] = [attachment_id, body_id]
    for index in range(4):
        edge_faces[f"connector_{index}"] = [f"attachment_{(index - 1) % 4}", f"attachment_{index}"]
    inventory = {
        "edges_by_id": edges,
        "face_edge_ids": face_edges,
        "edge_face_ids": edge_faces,
    }

    retained, termination, span = pipeline._attachment_adjacency_chains(
        inventory,
        set(edges),
        [f"footprint_{index}" for index in range(4)],
        ["support"],
    )

    assert retained == [f"retained_{index}" for index in range(4)]
    assert termination == [f"connector_{index}" for index in range(4)]
    assert span == sorted(
        [f"footprint_{index}" for index in range(4)]
        + [f"retained_{index}" for index in range(4)]
    )
    assert set(span).isdisjoint(termination)
    assert pipeline._attachment_footprint_candidates(
        inventory,
        retained,
        [f"footprint_{index}" for index in range(4)],
        ["support"],
    ) == {
        f"retained_{index}": (f"footprint_{index}",)
        for index in range(4)
    }


def test_representable_step_passes_actual_default_axis_first_mapping(tmp_path):
    path = write_axis_first_representable_step(tmp_path / "representable.step")
    shape, source = step_audit.load_step_source(path)
    frame = step_audit.resolve_canonical_frame(shape, source)
    semantics = step_audit.classify_impeller_semantics(shape, source, frame)

    result = pipeline.build_measurement_bundle(shape, source, frame, semantics)
    measurements = result.measurements
    expected_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert measurements["provenance"]["source_sha256"] == expected_sha == source["sha256"]
    assert measurements["provenance"]["source_entity_ids"] == sorted(
        record["face_id"] for record in source["faces"]
    )
    assert all(
        5 <= len(family["stations"]) <= 9
        for family in measurements["section_families"].values()
    )
    for family in measurements["section_families"].values():
        for station in family["stations"]:
            for name in ("side_a", "side_b", "leading_edge", "trailing_edge"):
                segment = station["decomposition"]["segments"][name]
                target = segment["nurbs_target"]
                assert target["degree"] >= 1
                assert target["knots"]
                assert target["weights"]
                assert target["control_points_local_mm"]
                assert target["sample_points_local_mm"]
                assert target["fit_evidence"]["residual"]["maximum_mm"] >= 0.0
                assert set(segment["source_ids"]) == set(
                    segment["source_edge_ids"]
                ) | set(segment["source_face_ids"])
        record = next(
            item
            for item in result.section_evidence["section_loop_records"]
            if item["population"] == family["population"]
            and item["h"] == station["h"]
        )
        assert record["exact_section"]["source_shape_scope"] == "complete_source_shape"
    for record in measurements["topology"]["material_measurements"].values():
        assert record["measurement_authority"] == (
            "occt_exact_brep_feature_measurement"
        )
        assert record["source_ids"]
    root = measurements["attachments"]["root"]
    assert float(np.median(root["lift_samples_mm"])) == pytest.approx(1.0, abs=0.15)

    with pytest.raises(V112MappingError) as exc_info:
        map_measurements_to_v112(
            measurements, tolerances=V112MappingTolerances()
        )
    assert getattr(exc_info.value, "reason", None) == "v116_v112_mapping_residual_exceeded"

    mapped = map_measurements_to_v112_review(
        measurements, tolerances=V112MappingTolerances()
    )
    assert mapped["mapping_status"] == "REJECTED_REVIEW_CANDIDATE"
    assert mapped["promotion"]["promotable"] is False
    assert "periodicity" in mapped["failed_terms"]
    assert mapped["geometry_patch_version"] == "1.1.2"
