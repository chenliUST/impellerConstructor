from __future__ import annotations

# ruff: noqa: E402

import copy
import hashlib
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

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
    V112MappingTolerances,
    map_measurements_to_v112,
)
from step_fixtures import (
    write_axis_first_impeller_step,
    write_axis_first_representable_step,
)
from part_rule_synthesis import impeller_v11_6_step_audit as step_audit


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
        lambda *_args, **_kwargs: (0.1, 0.9),
    )
    monkeypatch.setattr(pipeline.section_recovery, "solve_meridional_correspondence", lambda *_args: correspondence)
    monkeypatch.setattr(pipeline.section_recovery, "build_ordered_span_profiles", lambda *_args: (profile, profile, profile))
    monkeypatch.setattr(pipeline.section_recovery, "make_occt_revolved_measurement_surface", lambda *_args, **_kwargs: "revolved")
    monkeypatch.setattr(pipeline, "_measurement_surface_in_source_frame", lambda surface, *_args: surface)
    monkeypatch.setattr(pipeline, "_meridional_unwrapped_projector", lambda *_args: (lambda _point: (0.0, 0.0), (0.0, 0.0, 1.0)))
    monkeypatch.setattr(
        pipeline.section_recovery,
        "decompose_section_loop",
        lambda _loop, **_kwargs: "decomposition",
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
    monkeypatch.setattr(pipeline, "_station_for_mapping", lambda h, *_args: {"h": h, "source_ids": ["side-a"]})
    monkeypatch.setattr(pipeline, "_decomposition_summary", lambda _value: {"segments": {}})
    def section_probe(source_shape, surface, **kwargs):
        assert source_shape is inventory["shape"]
        assert set(kwargs["source_faces_by_id"]) == set(inventory["faces_by_id"])
        assert set(kwargs["allowed_source_face_ids"]) == set(instance["source_face_ids"])
        assert kwargs["source_shape_scope"] == "complete_source_shape"
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

    root_h, tip_h = pipeline._measured_active_span_interval(
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

    mapped = map_measurements_to_v112(
        measurements, tolerances=V112MappingTolerances()
    )
    assert mapped["mapping_status"] == "PASS"
    assert mapped["promotion"]["promotable"] is True
    assert mapped["geometry_patch_version"] == "1.1.2"
