from __future__ import annotations

# ruff: noqa: E402

import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))

import part_rule_synthesis.impeller_v11_6_source_frame as source_frame_module
from part_rule_synthesis.impeller_v11_6_source_frame import (
    AxisConsensusError,
    _authenticate_periodic_seed_group,
    _periodic_signature_group,
    _refined_span_cells,
    _rotational_surface_authority_group_check,
    _sample_trimmed_face_material_domain,
    _split_cross_blade_seed_component,
    coarse_periodic_face_partition,
    resolve_canonical_frame,
)
from part_rule_synthesis.impeller_v11_6_periodic_blades import (
    recover_periodic_blade_populations,
)
from part_rule_synthesis.impeller_v11_6_step_audit import (
    classify_impeller_semantics,
    load_step_source,
)
from part_rule_synthesis.impeller_v11_6_section_recovery import (
    LocalSectionFrame,
    SectionRecoveryError,
    section_full_source_solid,
)
from step_fixtures import (
    axis_first_fixture_expectations,
    write_ambiguous_axis_step,
    write_axis_first_impeller_step,
    write_displaced_parallel_axis_step,
    write_open_section_loop_step,
)


def _axis_line_distance(origin, expected_origin, expected_direction) -> float:
    direction = np.asarray(expected_direction, dtype=float)
    direction /= np.linalg.norm(direction)
    return float(
        np.linalg.norm(
            np.cross(np.asarray(origin) - np.asarray(expected_origin), direction)
        )
    )


def test_near_duplicate_bspline_knots_do_not_create_empty_segment_cells():
    cells = _refined_span_cells([0.0, 1.0, 1.0 + 5.0e-13], 4)

    assert cells == pytest.approx(
        [(0.0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0)]
    )


def test_uncertified_face_extrema_fall_back_to_exact_trim_boundary_without_promotion(
    monkeypatch,
):
    import cadquery as cq

    face = cq.Workplane("XY").box(10.0, 8.0, 2.0).faces(">Z").val()

    def reject_interior_extrema(*args, **kwargs):
        raise AxisConsensusError(
            "v116_source_sampling_extrema_not_converged",
            "synthetic non-convergence",
            {"source_face_id": "source_face_test"},
        )

    monkeypatch.setattr(
        source_frame_module,
        "_sample_trimmed_face_material_domain",
        reject_interior_extrema,
    )
    signature = source_frame_module._face_signature(
        face,
        {
            "face_id": "source_face_test",
            "geometry_type": face.geomType(),
            "area_mm2": float(face.Area()),
            "centroid_mm": list(face.Center().toTuple()),
        },
        np.eye(4),
        {"source_face_test": []},
    )

    assert signature["sampling_evidence"]["promotable"] is False
    assert signature["sampling_evidence"]["independent_validation_status"] == "UNKNOWN"
    assert signature["sampling_evidence"]["fallback_reason"] == (
        "v116_source_sampling_extrema_not_converged"
    )
    assert signature["sampling_evidence"]["exact_boundary_sample_count"] > 0


def test_analytic_axis_consensus_ignores_auxiliary_holes_and_is_deterministic(tmp_path):
    path = write_axis_first_impeller_step(
        tmp_path / "open-with-holes.step",
        blade_count=8,
        auxiliary_holes=True,
        root_blend_radius_mm=0.18,
    )
    shape, source = load_step_source(path)

    frame = resolve_canonical_frame(shape, source)

    assert frame == resolve_canonical_frame(shape, source)
    assert frame["method"] == "deterministic_analytic_axis_consensus_r3"
    assert frame["scale"] == 1.0
    assert frame["primary_icp_applied"] is False
    assert np.dot(frame["source_axis_direction"], [0.0, 0.0, 1.0]) > 0.999999
    direction_evidence = frame["axis_consensus"]["direction_resolution"]
    assert direction_evidence["method"] == (
        "small_radius_eye_positive_z_from_radial_weighted_axial_asymmetry"
    )
    assert direction_evidence["canonical_positive_z_role"] == (
        "large_radius_backplate_to_small_radius_eye"
    )
    assert direction_evidence["signed_normalized_moment"] > 0.0
    assert (
        _axis_line_distance(
            frame["source_axis_origin_mm"], [0.0, 0.0, 0.0], [0.0, 0.0, 1.0]
        )
        < 1.0e-7
    )
    selected = frame["axis_consensus"]["selected_cluster"]
    assert selected["source_entity_ids"]
    assert selected["confidence"]
    assert selected["coordinate_frame"] == "source_cartesian_mm"
    assert selected["units"]["linear"] == "mm"
    assert selected["tolerance"]
    assert selected["residual"]
    assert selected["provenance"]["source_entity_ids"] == selected[
        "source_entity_ids"
    ]
    assert selected["score_components"]["analytic_area_mm2"] > 0.0
    assert selected["score_components"]["analytic_feature_count"] >= 2
    assert "periodic_closure_support" in selected["score_components"]
    residual = frame["axis_consensus"]["residual"]
    assert (
        residual["line_rms_mm"]
        <= frame["axis_consensus"]["tolerance"]["line_distance_mm"]
    )
    assert residual["angular_spread_deg"] <= 0.05


def test_coarse_face_signatures_partition_periodic_and_nonperiodic_faces(tmp_path):
    blade_count = 8
    path = write_axis_first_impeller_step(
        tmp_path / "decoy.step",
        blade_count=blade_count,
        large_nonperiodic_decoy=True,
    )
    shape, source = load_step_source(path)
    frame = resolve_canonical_frame(shape, source)

    partition = coarse_periodic_face_partition(shape, source, frame)
    repeated_partition = coarse_periodic_face_partition(shape, source, frame)

    first_telemetry = partition["sampling_budget"].pop("wall_clock_telemetry")
    repeated_telemetry = repeated_partition["sampling_budget"].pop(
        "wall_clock_telemetry"
    )
    assert partition == repeated_partition
    assert first_telemetry["status"] == "DIAGNOSTIC_ONLY"
    assert repeated_telemetry["affects_certification"] is False
    assert partition["invariants"]["all_source_faces_accounted_for"] is True
    assert set(partition["periodic_face_ids"]).isdisjoint(
        partition["nonperiodic_face_ids"]
    )
    assert (
        len(partition["periodic_face_ids"]) + len(partition["nonperiodic_face_ids"])
        == source["face_count"]
    )
    assert blade_count in {
        group["count"] for group in partition["periodic_signature_groups"]
    }
    signatures = {item["source_face_id"]: item for item in partition["face_signatures"]}
    task5_fields = {
        "is_periodic",
        "blade_related",
        "periodic_membership",
        "canonical_surface_samples_mm",
        "streamwise_bounds_mm",
        "streamwise_coordinate",
        "radial_bounds_mm",
        "axial_bounds_mm",
        "angular_span_deg",
        "angular_span_evidence",
        "wrap_deg",
        "wrap_evidence",
        "source_frame_phase_deg",
        "canonical_frame_phase_deg",
        "phase_frame_evidence",
    }
    for face_id, signature in signatures.items():
        assert task5_fields <= signature.keys()
        assert signature["canonical_surface_samples_mm"]
        assert signature["streamwise_coordinate"] == "canonical_radius_mm"
        assert signature["streamwise_bounds_mm"] == signature["radial_bounds_mm"]
        assert (
            signature["streamwise_bounds_mm"][0] <= signature["streamwise_bounds_mm"][1]
        )
        assert signature["axial_bounds_mm"][0] <= signature["axial_bounds_mm"][1]
        assert signature["angular_span_evidence"]["method"]
        assert signature["wrap_evidence"]["method"]
        membership = signature["periodic_membership"]
        if face_id in partition["periodic_face_ids"]:
            assert signature["is_periodic"] is True
            assert signature["blade_related"] is True
            assert membership["status"] == "accepted_periodic_blade_related"
            assert membership["group_id"]
            assert membership["closure_within_tolerance"] is True
        else:
            assert signature["is_periodic"] is False
            assert signature["blade_related"] is False
            assert membership["group_id"] is None
            assert membership["closure_within_tolerance"] is False
    for component in [
        *partition["periodic_components"],
        *partition["nonperiodic_components"],
    ]:
        assert component["confidence"]
        assert component["coordinate_frame"] == "canonical_cylindrical_r_theta_z"
        assert component["units"]["linear"] == "mm"
        assert component["tolerance"]
        assert component["residual"]
        assert component["provenance"]["source_entity_ids"]
    assert any(
        signatures[face_id]["geometry_type"] == "PLANE"
        and signatures[face_id]["area_mm2"] > 500.0
        for face_id in partition["nonperiodic_face_ids"]
    )
    populations = recover_periodic_blade_populations(
        partition["face_signatures"], source["adjacency"]
    )
    assert populations["main_blade_count"] == blade_count
    assert populations["splitter_blade_count"] == 0
    assert populations["closure_diagnostics"]["all_populations_closed"] is True
    assert len(partition["periodic_components"]) == blade_count
    assert all(
        component["face_count"] >= 4
        and component["component_completeness"]["status"] == "COMPLETE"
        and len(component["component_completeness"]["blade_side_face_ids"]) == 2
        and len(component["component_completeness"]["root_edge_face_ids"]) >= 2
        for component in partition["periodic_components"]
    )

    synthetic_signatures = []
    synthetic_adjacency: dict[str, list[str]] = {}
    synthetic_groups = {}
    synthetic_seed_ids = []
    for instance in range(3):
        local_ids = [f"seed_{instance}", f"side_{instance}", f"edge_a_{instance}", f"edge_b_{instance}"]
        synthetic_seed_ids.append(local_ids[0])
        for face_id in local_ids:
            synthetic_signatures.append(
                {"source_face_id": face_id, "signature_hash": face_id.split("_")[0], "area_mm2": 10.0}
            )
        synthetic_adjacency[local_ids[0]] = [local_ids[1]]
        synthetic_adjacency[local_ids[1]] = [local_ids[0], local_ids[2]]
        synthetic_adjacency[local_ids[2]] = [local_ids[1], local_ids[3]]
        synthetic_adjacency[local_ids[3]] = [local_ids[2], f"support_{instance}"]
        synthetic_groups[local_ids[0]] = {
            "group_id": "synthetic_seed_group",
            "count": 3,
        }
        support_id = f"support_{instance}"
        synthetic_signatures.append(
            {"source_face_id": support_id, "signature_hash": "hub_support", "area_mm2": 100.0}
        )
        synthetic_adjacency[support_id] = [
            local_ids[3],
            f"support_{(instance - 1) % 3}",
            f"support_{(instance + 1) % 3}",
        ]
    split = _split_cross_blade_seed_component(
        [item["source_face_id"] for item in synthetic_signatures],
        synthetic_seed_ids,
        synthetic_adjacency,
        synthetic_signatures,
        synthetic_groups,
    )
    assert split["status"] == "PASS"
    assert sorted(len(item) for item in split["component_face_ids"]) == [4, 4, 4]
    assert set(split["evidence"]["excluded_support_face_ids"]) == {
        "support_0",
        "support_1",
        "support_2",
    }


def test_unknown_complex_bspline_with_large_trim_residual_is_not_authenticated():
    members = []
    for index in range(3):
        members.append(
            {
                "source_face_id": f"source_face_{index:05d}",
                "geometry_type": "BSPLINE",
                "radial_bounds_mm": [15.0, 45.0],
                "streamwise_bounds_mm": [15.0, 45.0],
                "angular_span_deg": 8.0,
                "sampling_evidence": {
                    "promotable": False,
                    "independent_validation_status": "UNKNOWN",
                    "rotational_surface_authority": {
                        "status": "PASS",
                        "comparison_payload": _surface_authority_payload(),
                    },
                },
            }
        )
    group = {
        "count": 3,
        "member_face_ids": [item["source_face_id"] for item in members],
        "angular_closure_residual_deg": 0.0,
        "trim_boundary_authentication": {
            "status": "FAIL",
            "residual_mm": 25.0,
            "tolerance_mm": 0.02,
            "within_tolerance": False,
            "method": "phase_aligned_exact_step_trim_boundary",
        },
    }

    evidence = _authenticate_periodic_seed_group(group, members, 50.0)

    assert evidence["accepted_as_periodic_blade_seed"] is False
    assert evidence["classification"] == "uncertified_coarse_sampling_population"
    assert evidence["checks"]["trim_boundary_authentication"]["residual_mm"] == 25.0
    assert evidence["checks"]["rotational_surface_authority"]["within_tolerance"] is True


def test_complex_bspline_seed_requires_exact_trim_boundary_and_surface_authority():
    reference = _surface_authority_payload()
    reordered = _surface_authority_payload(
        records=[
            [1, 1, 10.0, 0.0, 0.0, 1.0],
            [1, 2, 21.0, 0.0, 0.0, 1.0],
            [2, 1, 20.0, 0.0, 0.0, 1.0],
            [2, 2, 11.0, 0.0, 0.0, 1.0],
        ]
    )
    members = [
        {
            "source_face_id": f"source_face_{index:05d}",
            "geometry_type": "BSPLINE",
            "radial_bounds_mm": [15.0, 45.0],
            "streamwise_bounds_mm": [15.0, 45.0],
            "angular_span_deg": 8.0,
            "sampling_evidence": {
                "promotable": True,
                "rotational_surface_authority": {
                    "status": "PASS",
                    "comparison_payload": reference if index != 1 else reordered,
                },
            },
        }
        for index in range(3)
    ]
    group = {
        "count": 3,
        "member_face_ids": [item["source_face_id"] for item in members],
        "angular_closure_residual_deg": 0.0,
        "trim_boundary_authentication": {
            "status": "PASS",
            "residual_mm": 0.01,
            "tolerance_mm": 0.02,
            "within_tolerance": True,
            "sample_count": 96,
            "method": "phase_aligned_exact_step_trim_boundary",
        },
    }

    evidence = _authenticate_periodic_seed_group(group, members, 50.0)

    assert evidence["accepted_as_periodic_blade_seed"] is False
    assert evidence["checks"]["requires_exact_complex_authentication"] is True
    assert evidence["checks"]["trim_boundary_authentication"]["within_tolerance"] is True
    assert evidence["checks"]["rotational_surface_authority"]["within_tolerance"] is False


def _surface_authority_payload(*, records=None):
    if records is None:
        records = [
            [1, 1, 10.0, 0.0, 0.0, 1.0],
            [1, 2, 11.0, 0.0, 0.0, 1.0],
            [2, 1, 20.0, 0.0, 0.0, 1.0],
            [2, 2, 21.0, 0.0, 0.0, 1.0],
        ]
    return {
        "u_degree": 1,
        "v_degree": 1,
        "u_periodic": False,
        "v_periodic": False,
        "u_knots": [0.0, 1.0],
        "v_knots": [0.0, 1.0],
        "u_multiplicities": [2, 2],
        "v_multiplicities": [2, 2],
        "control_lattice_shape": [2, 2],
        "control_records_uv_local_xyz_weight": records,
        "knot_normalization": {
            "method": "affine_normalization_to_unit_interval",
            "u_transform": "(u-u_min)/(u_max-u_min)",
            "v_transform": "(v-v_min)/(v_max-v_min)",
        },
    }


def test_surface_authority_preserves_lattice_and_rejects_arbitrary_reordering():
    reference = _surface_authority_payload()
    reordered = _surface_authority_payload(
        records=[
            [1, 1, 10.0, 0.0, 0.0, 1.0],
            [1, 2, 21.0, 0.0, 0.0, 1.0],
            [2, 1, 20.0, 0.0, 0.0, 1.0],
            [2, 2, 11.0, 0.0, 0.0, 1.0],
        ]
    )
    members = [
        {
            "source_face_id": "source_face_00000",
            "sampling_evidence": {
                "rotational_surface_authority": {
                    "status": "PASS",
                    "comparison_payload": reference,
                }
            },
        },
        {
            "source_face_id": "source_face_00001",
            "sampling_evidence": {
                "rotational_surface_authority": {
                    "status": "PASS",
                    "comparison_payload": reordered,
                }
            },
        },
    ]

    check = _rotational_surface_authority_group_check(members)

    assert check["within_tolerance"] is False
    assert check["maximum_control_record_residual"] > check["tolerance"]["linear_mm"]

    reversed_u = _surface_authority_payload(
        records=[
            [1, 1, 20.0, 0.0, 0.0, 1.0],
            [1, 2, 21.0, 0.0, 0.0, 1.0],
            [2, 1, 10.0, 0.0, 0.0, 1.0],
            [2, 2, 11.0, 0.0, 0.0, 1.0],
        ]
    )
    reversed_members = [
        {
            "source_face_id": "source_face_00000",
            "sampling_evidence": {
                "rotational_surface_authority": {
                    "status": "PASS",
                    "comparison_payload": reference,
                }
            },
        },
        {
            "source_face_id": "source_face_00001",
            "sampling_evidence": {
                "rotational_surface_authority": {
                    "status": "PASS",
                    "comparison_payload": reversed_u,
                }
            },
        },
    ]

    reversed_check = _rotational_surface_authority_group_check(reversed_members)

    assert reversed_check["within_tolerance"] is True
    assert reversed_check["selected_parameterization_transforms"] == ["reverse_u"]
    assert reversed_check["knot_normalization"]["method"] == (
        "affine_normalization_to_unit_interval"
    )

    reordered_records = _surface_authority_payload(
        records=[
            [1, 2, 11.0, 0.0, 0.0, 1.0],
            [1, 1, 10.0, 0.0, 0.0, 1.0],
            [2, 1, 20.0, 0.0, 0.0, 1.0],
            [2, 2, 21.0, 0.0, 0.0, 1.0],
        ]
    )
    record_order_check = _rotational_surface_authority_group_check(
        [
            members[0],
            {
                "source_face_id": "source_face_00001",
                "sampling_evidence": {
                    "rotational_surface_authority": {
                        "status": "PASS",
                        "comparison_payload": reordered_records,
                    }
                },
            },
        ]
    )
    assert record_order_check["within_tolerance"] is False


def test_slow_wall_clock_cannot_change_partition_or_hash(tmp_path, monkeypatch):
    path = write_axis_first_impeller_step(tmp_path / "slow-clock.step", blade_count=5)
    shape, source = load_step_source(path)
    frame = resolve_canonical_frame(shape, source)
    baseline = coarse_periodic_face_partition(shape, source, frame)
    ticks = iter(range(0, 100_000_000, 10_000))
    monkeypatch.setattr(source_frame_module.time, "perf_counter", lambda: next(ticks))

    slowed = coarse_periodic_face_partition(shape, source, frame)

    baseline_telemetry = baseline["sampling_budget"].pop("wall_clock_telemetry")
    slowed_telemetry = slowed["sampling_budget"].pop("wall_clock_telemetry")
    assert slowed == baseline
    assert slowed["sampling_budget"]["wall_clock_budget_enforced"] is False
    assert baseline_telemetry["affects_certification"] is False
    assert slowed_telemetry["affects_sampling_budget"] is False


def test_curved_face_samples_lie_on_trimmed_brep_and_bound_emitted_extents(tmp_path):
    import cadquery as cq

    path = write_axis_first_impeller_step(
        tmp_path / "trimmed-samples.step",
        blade_count=6,
        root_blend_radius_mm=0.18,
    )
    shape, source = load_step_source(path)
    frame = resolve_canonical_frame(shape, source)
    partition = coarse_periodic_face_partition(shape, source, frame)
    signatures = {
        item["source_face_id"]: item for item in partition["face_signatures"]
    }
    checked = 0
    canonical_to_source = np.linalg.inv(
        np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    )

    for record, face in zip(source["faces"], shape.Faces(), strict=True):
        if face.geomType() == "PLANE":
            continue
        signature = signatures[record["face_id"]]
        samples = np.asarray(signature["canonical_surface_samples_mm"], dtype=float)
        radii = np.linalg.norm(samples[:, :2], axis=1)
        axial = samples[:, 2]

        assert signature["sampling_evidence"]["interior_material_sample_count"] > 0
        assert signature["sampling_evidence"]["face_center_of_mass_used"] is False
        assert len(samples) > len(face.Vertices())
        assert np.min(radii) >= signature["radial_bounds_mm"][0] - 0.0011
        assert np.max(radii) <= signature["radial_bounds_mm"][1] + 0.0011
        assert np.min(axial) >= signature["axial_bounds_mm"][0] - 0.0011
        assert np.max(axial) <= signature["axial_bounds_mm"][1] + 0.0011
        angular_start = signature["angular_span_evidence"]["start_angle_deg"]
        angular_span = signature["angular_span_deg"]
        sample_angles = (
            np.degrees(np.arctan2(samples[:, 1], samples[:, 0])) % 360.0
        )
        angular_offsets = (sample_angles - angular_start) % 360.0
        assert all(
            offset <= angular_span + 1.0e-5 or 360.0 - offset <= 1.0e-5
            for offset in angular_offsets
        )
        for point in samples[:: max(1, len(samples) // 12)]:
            source_point = canonical_to_source @ np.asarray([*point, 1.0])
            assert face.distance(cq.Vertex.makeVertex(*source_point[:3])) <= 1.0e-6
        checked += 1

    assert checked > 0


def test_trimmed_bspline_sampling_converges_to_independent_dense_extrema():
    import cadquery as cq
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.gp import gp_Pnt

    points = TColgp_Array2OfPnt(1, 7, 1, 7)
    for u_index in range(1, 8):
        for v_index in range(1, 8):
            u = (u_index - 1) / 6.0
            v = (v_index - 1) / 6.0
            peak = 3.75 * math.exp(
                -((u - 0.37) ** 2 / 0.012 + (v - 0.63) ** 2 / 0.018)
            )
            points.SetValue(u_index, v_index, gp_Pnt(20.0 + 8.0 * u, 6.0 * v, peak))
    builder = GeomAPI_PointsToBSplineSurface()
    builder.Interpolate(points)
    wrapped = BRepBuilderAPI_MakeFace(builder.Surface(), 1.0e-8).Face()
    face = cq.Face(wrapped)

    _, extent_points, _, _, evidence = _sample_trimmed_face_material_domain(
        face, canonical_matrix=np.eye(4)
    )
    adaptor = BRepAdaptor_Surface(face.wrapped)
    u_min, u_max, v_min, v_max = evidence["uv_bounds"]
    dense_max_z = max(
        adaptor.Value(float(u), float(v)).Z()
        for u in np.linspace(u_min, u_max, 301)
        for v in np.linspace(v_min, v_max, 301)
    )

    assert evidence["converged"] is True
    assert evidence["sample_levels"][-1]["density"] >= 33
    assert evidence["rejected_outside_uv_count"] >= 0
    assert evidence["extrema_error_tolerance_mm"] <= 0.01
    assert abs(float(np.max(extent_points[:, 2])) - dense_max_z) <= evidence[
        "extrema_error_tolerance_mm"
    ]


def test_trimmed_degree_one_bspline_captures_narrow_five_mm_knot_peak():
    import cadquery as cq
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BSplineSurface
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    from OCP.gp import gp_Pnt

    poles = TColgp_Array2OfPnt(1, 4, 1, 2)
    for u_index, (x_value, z_value) in enumerate(
        ((0.0, 0.0), (0.497, 5.0), (0.503, 5.0), (1.0, 0.0)), 1
    ):
        for v_index, y_value in enumerate((0.0, 1.0), 1):
            poles.SetValue(u_index, v_index, gp_Pnt(x_value, y_value, z_value))
    u_knots = TColStd_Array1OfReal(1, 4)
    u_multiplicities = TColStd_Array1OfInteger(1, 4)
    for index, value in enumerate((0.0, 0.497, 0.503, 1.0), 1):
        u_knots.SetValue(index, value)
        u_multiplicities.SetValue(index, 2 if index in {1, 4} else 1)
    v_knots = TColStd_Array1OfReal(1, 2)
    v_multiplicities = TColStd_Array1OfInteger(1, 2)
    for index, value in enumerate((0.0, 1.0), 1):
        v_knots.SetValue(index, value)
        v_multiplicities.SetValue(index, 2)
    surface = Geom_BSplineSurface(
        poles,
        u_knots,
        v_knots,
        u_multiplicities,
        v_multiplicities,
        1,
        1,
        False,
        False,
    )
    face = cq.Face(BRepBuilderAPI_MakeFace(surface, 1.0e-8).Face())

    _, extent_points, _, _, evidence = _sample_trimmed_face_material_domain(
        face, canonical_matrix=np.eye(4), source_face_id="narrow_degree_one_peak"
    )

    assert float(np.max(extent_points[:, 2])) == pytest.approx(5.0, abs=1.0e-9)
    assert evidence["converged"] is True
    assert evidence["independent_validation_status"] == "PASS"
    assert evidence["knot_evidence"]["u_degree"] == 1
    assert 0.497 in evidence["knot_evidence"]["u_breaks"]
    assert 0.503 in evidence["knot_evidence"]["u_breaks"]
    assert evidence["per_face_budget"]["status"] == "PASS"


def test_narrow_trimmed_bspline_refines_past_sixteen_to_close_local_control_bounds():
    import cadquery as cq
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BSplineSurface
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    from OCP.gp import gp_Pnt

    poles = TColgp_Array2OfPnt(1, 4, 1, 2)
    for u_index, (x_value, z_value) in enumerate(
        ((20.0, 0.0), (23.0, 100.0), (27.0, 0.0), (30.0, 0.0)), 1
    ):
        for v_index, y_value in enumerate((0.0, 1.0), 1):
            poles.SetValue(u_index, v_index, gp_Pnt(x_value, y_value, z_value))
    u_knots = TColStd_Array1OfReal(1, 2)
    u_multiplicities = TColStd_Array1OfInteger(1, 2)
    v_knots = TColStd_Array1OfReal(1, 2)
    v_multiplicities = TColStd_Array1OfInteger(1, 2)
    for index, value in enumerate((0.0, 1.0), 1):
        u_knots.SetValue(index, value)
        u_multiplicities.SetValue(index, 4)
        v_knots.SetValue(index, value)
        v_multiplicities.SetValue(index, 2)
    surface = Geom_BSplineSurface(
        poles,
        u_knots,
        v_knots,
        u_multiplicities,
        v_multiplicities,
        3,
        1,
        False,
        False,
    )
    face = cq.Face(
        BRepBuilderAPI_MakeFace(surface, 0.02, 0.98, 0.45, 0.55, 1.0e-8).Face()
    )

    _, _, _, _, evidence = _sample_trimmed_face_material_domain(
        face,
        canonical_matrix=np.eye(4),
        source_face_id="narrow_trim_requires_priority_refinement",
    )

    uniform_levels = [
        level
        for level in evidence["sample_levels"]
        if level.get("mode") != "priority_queue_local_knot_branch_subdivision"
    ]
    priority = evidence["priority_refinement_evidence"]
    assert uniform_levels[-1]["material_control_bound_gap_mm"] > 0.01
    assert uniform_levels[-1]["refinement_per_knot_span"] < 16
    assert priority["converged"] is True
    assert priority["maximum_refinement"] > 16
    assert priority["control_bound_gap_mm"] <= 0.01
    assert evidence["per_face_budget"]["consumed_samples"] < evidence[
        "per_face_budget"
    ]["maximum_samples"]


def test_five_mm_control_bound_gap_cannot_report_false_convergence(monkeypatch):
    import cadquery as cq
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_BSplineSurface
    from OCP.TColgp import TColgp_Array2OfPnt
    from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
    from OCP.gp import gp_Pnt

    poles = TColgp_Array2OfPnt(1, 2, 1, 2)
    for u_index, x_value in enumerate((0.0, 1.0), 1):
        for v_index, y_value in enumerate((0.0, 1.0), 1):
            poles.SetValue(u_index, v_index, gp_Pnt(x_value, y_value, 0.0))
    knots = TColStd_Array1OfReal(1, 2)
    multiplicities = TColStd_Array1OfInteger(1, 2)
    for index, value in enumerate((0.0, 1.0), 1):
        knots.SetValue(index, value)
        multiplicities.SetValue(index, 2)
    surface = Geom_BSplineSurface(
        poles,
        knots,
        knots,
        multiplicities,
        multiplicities,
        1,
        1,
        False,
        False,
    )
    face = cq.Face(BRepBuilderAPI_MakeFace(surface, 1.0e-8).Face())
    monkeypatch.setattr(
        source_frame_module,
        "_material_domain_control_bounds",
        lambda *args, **kwargs: np.asarray([0.0, math.sqrt(2.0), 0.0, 5.0]),
    )
    monkeypatch.setattr(
        source_frame_module,
        "_priority_refine_material_control_bounds",
        lambda *args, **kwargs: {
            "converged": False,
            "control_bounds": np.asarray([0.0, math.sqrt(2.0), 0.0, 5.0]),
            "control_bound_gap_mm": 5.0,
            "sampled_extrema_mm": [0.0, math.sqrt(2.0), 0.0, 0.0],
            "iterations": 128,
            "maximum_refinement": 128,
            "refined_branch_count_by_depth": {"5": 64, "6": 128, "7": 256},
        },
    )

    with pytest.raises(AxisConsensusError) as raised:
        _sample_trimmed_face_material_domain(
            face,
            canonical_matrix=np.eye(4),
            source_face_id="adversarial_hidden_five_mm_peak",
        )

    assert raised.value.reason == "v116_source_sampling_extrema_not_converged"
    assert raised.value.details["promotable"] is False
    assert raised.value.details["priority_refinement_evidence"][
        "control_bound_gap_mm"
    ] == 5.0


def test_repeated_connected_auxiliary_holes_do_not_enter_blade_handoff(tmp_path):
    blade_count = 6
    path = write_axis_first_impeller_step(
        tmp_path / "repeated-counterbores.step",
        blade_count=blade_count,
        repeated_connected_auxiliary_holes=True,
    )
    shape, source = load_step_source(path)
    frame = resolve_canonical_frame(shape, source)
    partition = coarse_periodic_face_partition(shape, source, frame)
    signatures = partition["face_signatures"]

    rejected_hole_faces = [
        signature
        for signature in signatures
        if signature["periodic_membership"]["status"]
        == "rejected_periodic_auxiliary_hole_feature"
    ]
    assert rejected_hole_faces
    assert all(signature["is_periodic"] is False for signature in rejected_hole_faces)
    assert all(
        signature["blade_related"] is False for signature in rejected_hole_faces
    )
    assert all(
        signature["rotational_repetition_detected"] is True
        for signature in rejected_hole_faces
    )
    assert all(
        signature["adjacency_expansion_stop"]["semantic_role"] == "auxiliary_hole"
        and signature["adjacency_expansion_stop"]["excluded"] is True
        for signature in rejected_hole_faces
    )
    populations = recover_periodic_blade_populations(signatures, source["adjacency"])
    assert populations["main_blade_count"] == blade_count
    assert populations["splitter_blade_count"] == 0


def test_rigidly_transformed_copy_has_same_canonical_signatures(tmp_path):
    base_path = write_axis_first_impeller_step(tmp_path / "base.step", blade_count=7)
    moved_path = write_axis_first_impeller_step(
        tmp_path / "moved.step",
        blade_count=7,
        rotation_deg=37.0,
        translation_mm=(11.0, -7.0, 4.0),
    )
    base_shape, base_source = load_step_source(base_path)
    moved_shape, moved_source = load_step_source(moved_path)

    base_frame = resolve_canonical_frame(base_shape, base_source)
    moved_frame = resolve_canonical_frame(moved_shape, moved_source)
    base_partition = coarse_periodic_face_partition(base_shape, base_source, base_frame)
    moved_partition = coarse_periodic_face_partition(
        moved_shape, moved_source, moved_frame
    )

    angle = math.radians(37.0)
    expected_direction = [math.sin(angle), 0.0, math.cos(angle)]
    assert np.dot(moved_frame["source_axis_direction"], expected_direction) > 0.999999
    assert (
        _axis_line_distance(
            moved_frame["source_axis_origin_mm"],
            [11.0, -7.0, 4.0],
            expected_direction,
        )
        < 1.0e-6
    )
    assert Counter(
        item["signature_hash"] for item in base_partition["face_signatures"]
    ) == Counter(item["signature_hash"] for item in moved_partition["face_signatures"])
    assert [
        group["count"] for group in base_partition["periodic_signature_groups"]
    ] == [group["count"] for group in moved_partition["periodic_signature_groups"]]


def test_opposite_world_axis_direction_resolves_from_source_geometry(tmp_path):
    path = write_axis_first_impeller_step(
        tmp_path / "flipped.step",
        blade_count=7,
        rotation_axis=(1.0, 0.0, 0.0),
        rotation_deg=180.0,
    )
    shape, source = load_step_source(path)

    frame = resolve_canonical_frame(shape, source)

    assert np.dot(frame["source_axis_direction"], [0.0, 0.0, -1.0]) > 0.999999
    assert (
        frame["axis_consensus"]["direction_resolution"]["method"]
        != "candidate_enumeration_order"
    )


def test_equivalent_analytic_axes_fail_with_stable_reason(tmp_path):
    path = write_ambiguous_axis_step(tmp_path / "ambiguous.step")
    shape, source = load_step_source(path)

    with pytest.raises(AxisConsensusError) as raised:
        resolve_canonical_frame(shape, source)

    assert raised.value.reason == "v116_axis_consensus_ambiguous"
    assert len(raised.value.details["competing_candidates"]) >= 2


def test_equal_score_displaced_parallel_axes_are_ambiguous(tmp_path, monkeypatch):
    path = write_displaced_parallel_axis_step(tmp_path / "parallel-ambiguous.step")
    shape, source = load_step_source(path)
    equal_candidates = [
        {
            "source_entity_id": f"source_face_{index:05d}",
            "source_kind": "face",
            "geometry_type": "CYLINDER",
            "line_origin": np.asarray([x_position, 0.0, 0.0]),
            "line_direction": np.asarray([0.0, 0.0, 1.0]),
            "analytic_area_mm2": 100.0,
            "radius_mm": 3.0,
        }
        for index, x_position in enumerate((-8.0, 8.0))
    ]
    monkeypatch.setattr(
        source_frame_module,
        "_extract_axis_candidates",
        lambda _shape: equal_candidates,
    )

    with pytest.raises(AxisConsensusError) as raised:
        resolve_canonical_frame(shape, source)

    assert raised.value.reason == "v116_axis_consensus_ambiguous"
    competitors = raised.value.details["competing_candidates"]
    assert len(competitors) >= 2
    assert competitors[0]["line_direction"] == competitors[1]["line_direction"]
    assert competitors[0]["line_origin_mm"] != competitors[1]["line_origin_mm"]


def test_transformed_sample_residual_uses_nonempty_canonical_surface_samples():
    members = []
    for index, angle_deg in enumerate((0.0, 120.0, 240.0)):
        angle = math.radians(angle_deg)
        z_offset = 0.12 if index == 1 else 0.0
        members.append(
            {
                "source_face_id": f"source_face_{index:05d}",
                "centroid_angle_deg": angle_deg,
                "centroid_rz_mm": [15.0, 2.0],
                "canonical_surface_samples_mm": [
                    [10.0 * math.cos(angle), 10.0 * math.sin(angle), 1.0],
                    [20.0 * math.cos(angle), 20.0 * math.sin(angle), 3.0 + z_offset],
                ],
            }
        )

    group = _periodic_signature_group("fixture-signature", members, 50.0)

    assert group is not None
    assert group["transformed_sample_residual_mm"] > 0.0
    assert group["residual"]["method"] == (
        "symmetric_nearest_neighbor_of_phase_aligned_canonical_surface_samples"
    )
    assert group["residual"]["canonical_surface_sample_count"] == 6

    no_samples = [
        {**member, "canonical_surface_samples_mm": []} for member in members
    ]
    assert _periodic_signature_group("fixture-signature", no_samples, 50.0) is None


def test_task2_fixture_contract_covers_splitter_shroud_measurements_and_open_loop(
    tmp_path,
):
    expected = axis_first_fixture_expectations(
        blade_count=6,
        splitter_count=6,
        splitter_phase_fraction=0.37,
        closed_shroud=True,
        root_blend_radius_mm=0.18,
    )
    wheel_path = write_axis_first_impeller_step(
        tmp_path / "main-splitter-closed.step",
        blade_count=6,
        splitter_count=6,
        splitter_phase_fraction=0.37,
        closed_shroud=True,
        root_blend_radius_mm=0.18,
    )
    open_loop_path = write_open_section_loop_step(tmp_path / "open-section.step")

    shape, source = load_step_source(wheel_path)
    frame = resolve_canonical_frame(shape, source)
    partition = coarse_periodic_face_partition(shape, source, frame)
    populations = recover_periodic_blade_populations(
        partition["face_signatures"], source["adjacency"]
    )
    semantics = classify_impeller_semantics(shape, source, frame)

    assert source["solid_count"] == 1
    assert expected["topology"] == "closed"
    assert expected["main_blade_count"] == expected["splitter_blade_count"] == 6
    assert expected["splitter_phase_deg"] != pytest.approx(
        0.5 * expected["main_pitch_deg"]
    )
    assert expected["main_section_thickness_mm"] == {"root": 2.7, "tip": 1.24}
    assert expected["root_lift_mm"] > 0.0
    assert expected["root_blend_geometry"] == "blade_to_hub_attachment_fillet"
    assert partition["periodic_face_ids"]
    assert populations["main_blade_count"] == 6
    assert populations["splitter_blade_count"] == 6
    assert semantics["main_blade_count"] == 6
    assert semantics["splitter_blade_count"] == 6
    assert semantics["shroud_topology"] == "undetermined"
    assert (
        semantics["shroud_topology_status"]
        == "pending_authenticated_support_recovery"
    )
    assert semantics["splitter_phase_deg"] == pytest.approx(
        populations["splitter"]["phase_relative_to_main_deg"]
    )
    assert frame["source_axis_origin_mm"] == pytest.approx(
        expected["axis"]["origin_mm"], abs=1.0e-6
    )
    assert frame["source_axis_direction"] == pytest.approx(
        expected["axis"]["direction"], abs=1.0e-9
    )
    matrix = np.asarray(frame["source_to_canonical_matrix"], dtype=float)
    assert matrix == pytest.approx(
        np.eye(4),
        abs=1.0e-12,
    )
    assert np.linalg.det(matrix[:3, :3]) == pytest.approx(1.0, abs=1.0e-12)
    assert matrix @ np.asarray([10.0, 2.0, 8.0, 1.0]) == pytest.approx(
        [10.0, 2.0, 8.0, 1.0], abs=1.0e-12
    )

    source_splitter_phase = expected["splitter_phase_deg"]
    source_main = np.asarray([100.0, 0.0, 8.0, 1.0])
    source_splitter = np.asarray(
        [
            100.0 * math.cos(math.radians(source_splitter_phase)),
            100.0 * math.sin(math.radians(source_splitter_phase)),
            8.0,
            1.0,
        ]
    )

    def transformed_phase(point: np.ndarray) -> float:
        transformed = matrix @ point
        return math.degrees(math.atan2(transformed[1], transformed[0])) % 360.0

    canonical_phase_oracle = (
        transformed_phase(source_splitter) - transformed_phase(source_main)
    ) % expected["main_pitch_deg"]
    relative_evidence = populations["splitter"]["relative_phase_evidence"]
    assert relative_evidence["source_frame_phase_relative_to_main_deg"] == pytest.approx(
        source_splitter_phase, abs=2.0e-5
    )
    assert relative_evidence[
        "canonical_frame_phase_relative_to_main_deg"
    ] == pytest.approx(canonical_phase_oracle, abs=2.0e-5)
    assert relative_evidence["handedness"] == "right_handed"
    assert relative_evidence["source_axis_direction"] == pytest.approx(
        [0.0, 0.0, 1.0], abs=1.0e-12
    )
    assert any(
        face.geomType() == "CYLINDER"
        and 0.79 <= face.BoundingBox().zmin <= 0.81
        and face.BoundingBox().zmax <= 1.01
        and max(face.BoundingBox().xlen, face.BoundingBox().ylen) > 5.0
        for face in shape.Faces()
    )
    assert open_loop_path.read_text(encoding="latin-1").startswith("ISO-10303-21;")


def test_large_outer_wall_does_not_authenticate_closed_shroud(tmp_path):
    path = write_axis_first_impeller_step(
        tmp_path / "large-wall.step",
        blade_count=8,
        large_nonperiodic_decoy=True,
    )
    shape, source = load_step_source(path)
    frame = resolve_canonical_frame(shape, source)
    semantics = classify_impeller_semantics(shape, source, frame)

    assert semantics["shroud_topology"] == "undetermined"
    assert (
        semantics["shroud_topology_status"]
        == "pending_authenticated_support_recovery"
    )


def test_open_loop_fixture_is_a_solid_and_reaches_exact_section_loop_validation(
    tmp_path,
):
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    path = write_open_section_loop_step(tmp_path / "open-section.step")
    shape, source = load_step_source(path)
    source_faces = {
        record["face_id"]: face
        for record, face in zip(source["faces"], shape.Faces(), strict=True)
    }
    vertical_face_ids = [
        face_id
        for face_id, face in source_faces.items()
        if face.BoundingBox().zlen > 1.9
    ]
    allowed_face_ids = sorted(vertical_face_ids)[:-1]

    assert source["solid_count"] == 1
    assert source["closed_solid"] is True
    assert len(vertical_face_ids) == 4
    with pytest.raises(SectionRecoveryError) as raised:
        section_full_source_solid(
            shape,
            gp_Pln(gp_Pnt(0.0, 0.0, 1.0), gp_Dir(0.0, 0.0, 1.0)),
            source_faces_by_id=source_faces,
            allowed_source_face_ids=allowed_face_ids,
            local_frame=LocalSectionFrame(
                (10.0, 0.0, 1.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ),
            source_tolerance_mm=1.0e-6,
            edge_sample_count=5,
        )

    assert raised.value.reason == "v116_section_loop_open"
