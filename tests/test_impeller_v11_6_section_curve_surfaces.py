import copy
import math

import numpy as np
import pytest

from part_rule_synthesis import impeller_v11_6_section_curve_surfaces as surfaces_module
from part_rule_synthesis.impeller_v11_3_parameter_inspection import (
    _blade_anchor_directions,
    _graph_blade_anchor_directions,
    _placement_parameter_matches_source,
    build_parameter_inspection_contract,
    parameter_inspection_generation_id,
)
from part_rule_synthesis.impeller_v11_6_section_curve_surfaces import (
    DirectSectionSurfaceError,
    _attachment_topology_contract,
    _build_population_grids,
    _closure_mode,
    _common_z_boundary_diagnostic,
    _coons_tip_grid,
    _copy_surface_graph_for_direct_replacement,
    _ordered_closed_trim_paths,
    _ordered_trim_paths_with_records,
    _replace_exact_trimmed_patch_surfaces,
    _remove_superseded_surface_failures,
    _sample_authenticated_trimmed_surface_patch,
    _sample_authenticated_trimmed_surface_patches,
    _sample_trim_polygon_quad_partition,
    _single_surface_quality,
    _source_boundary_samples,
    replace_blade_surfaces_with_direct_section_curves,
)


def test_diagnostic_timing_survives_a_detached_stdout_pipe(monkeypatch, tmp_path):
    timing_path = tmp_path / "timing.log"
    monkeypatch.setenv("V116_R16_DIAGNOSTIC_TIMING", "1")
    monkeypatch.setenv("V116_R16_DIAGNOSTIC_TIMING_PATH", str(timing_path))

    def closed_stdout(*_args, **_kwargs):
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr("builtins.print", closed_stdout)
    surfaces_module._emit_r16_timing(
        "detached_worker",
        surfaces_module.time.perf_counter(),
        surface_count=3,
    )

    assert "label=detached_worker" in timing_path.read_text(encoding="utf-8")


def test_direct_surface_loft_interpolates_measured_curves_and_periodic_instances():
    graph, manifest = replace_blade_surfaces_with_direct_section_curves(
        _graph(), _mapping(), span_sample_count=9, curve_sample_count=17
    )

    first = _surface(graph, 0, "blade_pressure")
    second = _surface(graph, 1, "blade_pressure")
    station_row = first["uv_grid"][4]
    expected = _curve_points(0.5, "side_a")
    for point in expected:
        assert min(math.dist(point, sample) for sample in station_row) < 1.0e-9
    assert np.asarray(second["uv_grid"]) == pytest.approx(
        _rotate_grid(first["uv_grid"], 180.0)
    )
    assert first["source"]["authority"] == (
        "authenticated_step_exact_section_curve_network"
    )
    assert manifest["generated_section_loops"][1]["authority"] == (
        "reconstructed_surface_carrier_intersection"
    )


def test_direct_surface_loft_keeps_independent_side_endpoints():
    graph, _manifest = replace_blade_surfaces_with_direct_section_curves(
        _graph(), _mapping(), span_sample_count=9, curve_sample_count=17
    )
    side_a = _surface(graph, 0, "blade_pressure")["uv_grid"][0]
    side_b = _surface(graph, 0, "blade_suction")["uv_grid"][0]
    assert math.dist(side_a[0], side_b[0]) > 2.0
    assert side_a[0][0] == pytest.approx(10.0)
    assert side_b[0][0] == pytest.approx(12.55)


def test_direct_surface_uses_curve_u_and_preserves_nonmonotone_physical_s():
    mapping = _mapping()
    stations = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["stations"]
    for station in stations:
        station["curves"]["side_b"]["s_physical_mm"] = [12.55, 16.0, 15.75]

    graph, _manifest = replace_blade_surfaces_with_direct_section_curves(
        _graph(), mapping, span_sample_count=9, curve_sample_count=17
    )

    assert _surface(graph, 0, "blade_suction")["uv_grid"]


def test_direct_surface_uses_common_source_face_parameter_not_local_chord_u():
    mapping = _mapping()
    stations = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["stations"]
    for station in stations:
        h = float(station["active_h"])
        side_a = [[0.0, 0.0, h], [2.5, 0.625, h], [10.0, 10.0, h]]
        side_b = [[0.0, 2.0, h], [2.5, 2.625, h], [10.0, 12.0, h]]
        station["closure_classification"] = "sharp_shared_seam"
        for role, points, face_id in (
            ("side_a", side_a, "source-pressure-face"),
            ("side_b", side_b, "source-suction-face"),
        ):
            station["curves"][role].update(
                {
                    "canonical_points_xyz_mm": points,
                    "u": [0.0, 0.5, 1.0],
                        "source_face_parameter": {
                        "face_id": face_id,
                        "uv": [[0.0, h], [0.25, h], [1.0, h]],
                            "projection_residual_max_mm": 1.0e-9,
                        },
                        "source_face_surface": _quadratic_source_surface(
                            face_id, 0.0 if role == "side_a" else 2.0
                        ),
                }
            )
        station["curves"]["leading_edge"]["canonical_points_xyz_mm"] = [
            side_b[0],
            [0.0, 1.0, h],
            side_a[0],
        ]
        station["curves"]["trailing_edge"]["canonical_points_xyz_mm"] = [
            side_a[-1],
            [10.0, 11.0, h],
            side_b[-1],
        ]

    graph, manifest = replace_blade_surfaces_with_direct_section_curves(
        _graph(), mapping, span_sample_count=9, curve_sample_count=17
    )

    pressure = _surface(graph, 0, "blade_pressure")["uv_grid"]
    suction = _surface(graph, 0, "blade_suction")["uv_grid"]
    assert pressure[0][0][0] == pytest.approx(0.0)
    assert pressure[0][-1][0] == pytest.approx(10.0)
    assert np.asarray(pressure).shape == np.asarray(suction).shape
    correspondence = manifest["populations"][0]["surface_correspondence"]
    assert correspondence["side_a"]["method"] == (
        "authenticated_source_face_trimmed_parameter_domain"
    )
    assert correspondence["side_a"]["source_parameter_axis"] == "u"
    assert correspondence["side_a"]["surface_evaluation"] == (
        "authenticated_source_nurbs_evaluated_from_trimmed_parameter_domain"
    )
    assert correspondence["side_a"]["station_curve_usage"] == (
        "authoritative_analytic_surface_incidence_constraint"
    )
    assert correspondence["side_a"]["stream_query_authority"] == (
        "source_surface_native_knots_and_uniform_samples"
    )
    assert correspondence["side_a"]["station_surface_incidence_residual_max_mm"] < 0.01
    assert correspondence["side_b"]["station_surface_incidence_residual_max_mm"] < 0.01
    quality = manifest["populations"][0]["surface_quality"]
    assert quality["status"] == "PASS"
    assert quality["foldover_count"] == 0
    assert quality["carrier_section_observation_is_geometry_gate"] is True
    assert quality["authoritative_station_residual_max_mm"] < 0.01
    assert _surface(graph, 0, "blade_pressure")["source"]["authority"] == (
        "authenticated_step_trimmed_rational_bspline_surface"
    )
    _native_grids, native_interpolation = _build_population_grids(
        stations,
        span_sample_count=9,
        curve_sample_count=17,
        native_source_stream_sampling=True,
    )
    native_correspondence = native_interpolation["surface_correspondence"]
    assert native_correspondence["side_a"]["stream_query_authority"] == (
        "source_surface_native_knots_and_uniform_samples"
    )


def test_exact_source_surface_rejects_station_curve_that_is_not_incident():
    mapping = _mapping()
    stations = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["stations"]
    for station in stations:
        h = float(station["active_h"])
        for role, y_offset, face_id in (
            ("side_a", 0.0, "source-pressure-face"),
            ("side_b", 2.0, "source-suction-face"),
        ):
            points = [[0.0, y_offset, h], [2.5, y_offset + 0.625, h], [10.0, y_offset + 10.0, h]]
            station["curves"][role].update(
                {
                    "canonical_points_xyz_mm": points,
                    "source_face_parameter": {
                        "face_id": face_id,
                        "uv": [[0.0, h], [0.25, h], [1.0, h]],
                        "projection_residual_max_mm": 0.0,
                    },
                    "source_face_surface": _quadratic_source_surface(
                        face_id, y_offset
                    ),
                }
            )
    stations[1]["curves"]["side_a"]["canonical_points_xyz_mm"][1][2] += 1.0

    with pytest.raises(DirectSectionSurfaceError) as caught:
        replace_blade_surfaces_with_direct_section_curves(
            _graph(), mapping, span_sample_count=9, curve_sample_count=17
        )

    assert caught.value.reason == "v116_direct_curve_surface_quality_failed"
    assert caught.value.details["authoritative_station_residual_max_mm"] > 0.9


def test_direct_surface_rejects_partial_source_face_parameter_authority():
    mapping = _mapping()
    stations = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["stations"]
    stations[0]["curves"]["side_a"]["source_face_parameter"] = {
        "face_id": "source-pressure-face",
        "uv": [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0]],
        "projection_residual_max_mm": 0.0,
    }

    with pytest.raises(DirectSectionSurfaceError) as caught:
        replace_blade_surfaces_with_direct_section_curves(
            _graph(), mapping, span_sample_count=9, curve_sample_count=17
        )

    assert caught.value.reason == "v116_direct_curve_correspondence_invalid"


def test_direct_root_and_open_tip_consume_the_same_section_boundaries():
    graph, _manifest = replace_blade_surfaces_with_direct_section_curves(
        _graph(with_attachments=True),
        _mapping(),
        span_sample_count=9,
        curve_sample_count=17,
    )
    pressure = _surface(graph, 0, "blade_pressure")["uv_grid"]
    suction = _surface(graph, 0, "blade_suction")["uv_grid"]
    root = _surface(graph, 0, "root_to_hub_attachment")["uv_grid"]
    tip = _surface(graph, 0, "open_tip_dome")["uv_grid"]

    assert root[-1][0] == pytest.approx(pressure[0][0])
    assert root[0][0][2] < root[-1][0][2]
    assert np.allclose(tip[0], pressure[-1])
    assert np.allclose(tip[-1], suction[-1])
    assert _surface(graph, 0, "root_to_hub_attachment")["source"]["construction"] == (
        "direct_hub_to_measurement_carrier"
    )


def test_exact_source_root_patches_replace_artificial_attachment_and_pattern():
    mapping = _mapping()
    authority = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["active_span_authority"]
    authority["root_surface_patches"] = [
        _quadratic_source_surface("source-root-patch-a", 3.0),
        _quadratic_source_surface("source-root-patch-b", 6.0),
    ]
    authority["root_surface_patch_authority"] = (
        "authenticated_step_trimmed_rational_bspline_surface"
    )

    source_graph = _graph(with_attachments=True)
    source_graph["parameter_inspection"] = build_parameter_inspection_contract(
        source_graph
    )
    graph, _manifest = replace_blade_surfaces_with_direct_section_curves(
        source_graph,
        mapping,
        span_sample_count=9,
        curve_sample_count=17,
    )

    roots = [
        surface
        for surface in graph["surfaces"]
        if surface.get("role") == "root_to_hub_attachment"
    ]
    assert len(roots) == 4
    assert {
        root["source"]["source_face_id"] for root in roots
    } == {"source-root-patch-a", "source-root-patch-b"}
    assert all(
        root["source"]["construction"] == "authenticated_source_root_patch"
        for root in roots
    )
    assert all(root["v1_1_root_quality"]["status"] == "PASS" for root in roots)
    assert len({root["face_family"] for root in roots}) == 2
    first = next(
        root
        for root in roots
        if root["blade_pair_index"] == 0
        and root["source"]["source_face_id"] == "source-root-patch-a"
    )
    second = next(
        root
        for root in roots
        if root["blade_pair_index"] == 1
        and root["source"]["source_face_id"] == "source-root-patch-a"
    )
    assert np.asarray(second["uv_grid"]) == pytest.approx(
        _rotate_grid(first["uv_grid"], 180.0)
    )
    _assert_parameter_inspection_matches_final_surfaces(graph)


def test_direct_surface_graph_copy_on_write_preserves_large_read_only_grids():
    source = _graph()
    source["surfaces"][0]["display"] = {"visible_by_default": True}
    source["transition_failures"] = [{"reason": "existing"}]

    copied = _copy_surface_graph_for_direct_replacement(source)

    assert copied is not source
    assert copied["surfaces"][0] is not source["surfaces"][0]
    assert copied["surfaces"][0]["uv_grid"] is source["surfaces"][0]["uv_grid"]
    assert copied["surfaces"][0]["display"] is not source["surfaces"][0]["display"]
    assert copied["transition_failures"] is not source["transition_failures"]


def test_exact_source_tip_patches_replace_coons_cap_and_pattern():
    mapping = _mapping()
    authority = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["active_span_authority"]
    authority["tip_surface_patches"] = [
        _quadratic_source_surface("source-tip-patch-a", 9.0),
        _quadratic_source_surface("source-tip-patch-b", 12.0),
    ]
    authority["tip_surface_patch_authority"] = (
        "authenticated_step_trimmed_rational_bspline_surface"
    )

    source_graph = _graph(with_attachments=True)
    source_graph["parameter_inspection"] = build_parameter_inspection_contract(
        source_graph
    )
    graph, _manifest = replace_blade_surfaces_with_direct_section_curves(
        source_graph,
        mapping,
        span_sample_count=9,
        curve_sample_count=17,
    )

    tips = [
        surface
        for surface in graph["surfaces"]
        if surface.get("role") == "open_tip_dome"
    ]
    assert len(tips) == 4
    assert {tip["source"]["source_face_id"] for tip in tips} == {
        "source-tip-patch-a",
        "source-tip-patch-b",
    }
    assert len({tip["face_family"] for tip in tips}) == 2
    assert all(
        tip["source"]["construction"]
        == "authenticated_source_open_tip_patch"
        for tip in tips
    )
    assert all(tip["v1_1_tip_quality"]["status"] == "PASS" for tip in tips)
    first = next(
        tip
        for tip in tips
        if tip["blade_pair_index"] == 0
        and tip["source"]["source_face_id"] == "source-tip-patch-a"
    )
    second = next(
        tip
        for tip in tips
        if tip["blade_pair_index"] == 1
        and tip["source"]["source_face_id"] == "source-tip-patch-a"
    )
    assert np.asarray(second["uv_grid"]) == pytest.approx(
        _rotate_grid(first["uv_grid"], 180.0)
    )
    _assert_parameter_inspection_matches_final_surfaces(graph)


def test_exact_source_edge_patches_replace_sharp_seam_placeholders():
    mapping = _mapping()
    family = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]
    for station in family["stations"]:
        station["closure_classification"] = "sharp_shared_seam"
    authority = family["active_span_authority"]
    authority["leading_edge_surface_patches"] = [
        _quadratic_source_surface("source-leading-patch", 20.0)
    ]
    authority["trailing_edge_surface_patches"] = [
        _quadratic_source_surface("source-trailing-patch", 30.0)
    ]

    graph, _manifest = replace_blade_surfaces_with_direct_section_curves(
        _graph(),
        mapping,
        span_sample_count=9,
        curve_sample_count=17,
    )

    for blade_index in (0, 1):
        leading = _surface(graph, blade_index, "blade_leading_edge")
        trailing = _surface(graph, blade_index, "blade_trailing_edge")
        assert leading["material"] is True
        assert trailing["material"] is True
        assert leading["export_default"] == "included"
        assert trailing["export_default"] == "included"
        assert leading["source"]["source_face_id"] == "source-leading-patch"
        assert trailing["source"]["source_face_id"] == "source-trailing-patch"
        assert leading["source"]["construction"] == (
            "authenticated_source_leading_edge_patch"
        )
        assert trailing["source"]["construction"] == (
            "authenticated_source_trailing_edge_patch"
        )
def test_placement_anchor_directions_follow_exact_root_subpatch_semantics():
    graph = {
        "blade_to_blade_loop_family": {
            "blades": [
                {"blade_class": "main"},
                {"blade_class": "main"},
            ]
        },
        "surfaces": [
            {
                "id": "blade_0_root_attachment_surface_source_patch_00",
                "blade_index": 0,
                "role": "root_to_hub_attachment",
                "source": {
                    "source_authority_index": 0,
                    "trim_subpatch_index": 0,
                },
                "uv_grid": [[[1.0, 0.0, 0.0]], [[1.0, 0.0, 1.0]]],
            },
            {
                "id": "blade_1_root_attachment_surface_source_patch_00",
                "blade_index": 1,
                "role": "root_to_hub_attachment",
                "source": {
                    "source_authority_index": 0,
                    "trim_subpatch_index": 0,
                },
                "uv_grid": [[[-1.0, 0.0, 0.0]], [[-1.0, 0.0, 1.0]]],
            },
        ],
    }

    assert _graph_blade_anchor_directions(graph, "main") == [
        [1.0, 0.0],
        [-1.0, 0.0],
    ]


def test_contract_and_validator_choose_the_same_exact_root_subpatch_anchor():
    surfaces = [
        _root_anchor_surface(0, 1, [0.0, 1.0, 1.0]),
        _root_anchor_surface(0, 0, [1.0, 0.0, 1.0]),
        _root_anchor_surface(1, 1, [0.0, -1.0, 1.0]),
        _root_anchor_surface(1, 0, [-1.0, 0.0, 1.0]),
    ]
    graph = {
        "blade_to_blade_loop_family": {
            "blades": [
                {"blade_class": "main"},
                {"blade_class": "main"},
            ]
        },
        "surfaces": surfaces,
    }
    blade_instances = {
        f"blade_{index}": {
            "blade_class": "main",
            "blade_index": index,
            "surface_ids": [
                surface["id"]
                for surface in surfaces
                if surface["blade_index"] == index
            ],
        }
        for index in (0, 1)
    }
    surface_by_id = {surface["id"]: surface for surface in surfaces}

    expected = [[1.0, 0.0], [-1.0, 0.0]]
    assert _blade_anchor_directions(
        blade_instances,
        surface_by_id,
        "main",
    ) == expected
    assert _graph_blade_anchor_directions(graph, "main") == expected


def test_angular_pitch_validation_accepts_step_sampling_noise_only():
    graph = {
        "blade_to_blade_loop_family": {
            "blades": [
                {"blade_class": "main"},
                {"blade_class": "main"},
            ]
        },
        "surfaces": [
            _root_anchor_surface(
                0,
                0,
                [10.282448935897529, 8.795640961808065, 1.0],
            ),
            _root_anchor_surface(
                1,
                0,
                [5.017116681388418, 12.566646181609206, 1.0],
            ),
        ],
    }
    parameter = {
        "parameter_id": "blade.angular_pitch_deg",
        "resolved_value": 360.0 / 13.0,
        "selection_scope": {"source_geometry_kind": "blade_placement"},
        "feature_geometry": [
            {
                "kind": "reference_axis",
                "origin": [0.0, 0.0, 0.0],
                "direction": [0.0, 0.0, 1.0],
                "rendering_role": "selected_feature",
            }
        ],
    }

    assert _placement_parameter_matches_source(parameter, graph)
    parameter["resolved_value"] += 1.0e-3
    assert not _placement_parameter_matches_source(parameter, graph)


def test_trim_sampler_treats_small_constant_edge_uv_noise_as_projection_noise():
    authority = _quadratic_source_surface("source-root-patch", 3.0)
    authority["trim_boundary_uv_paths"][0]["uv"] = [
        [0.0, -2.0e-8],
        [0.5, 1.0e-4],
        [1.0, -2.0e-8],
    ]
    authority["trim_boundary_uv_paths"][2]["uv"] = [
        [1.0, 1.00000002],
        [0.5, 0.99985],
        [0.0, 1.00000002],
    ]

    sampled, evidence = _sample_authenticated_trimmed_surface_patch(
        authority,
        stream_sample_count=33,
        span_sample_count=17,
    )

    assert evidence["stream_axis"] in {"u", "v"}
    assert evidence["surface_quality"]["status"] == "PASS"
    assert evidence["surface_quality"]["foldover_count"] == 0
    assert _single_surface_quality(sampled)["status"] == "PASS"


def test_trim_path_order_accepts_source_projection_scale_seam_noise():
    authority = _quadratic_source_surface("source-seam-noise", 0.0)
    authority["trim_boundary_uv_paths"][-1]["uv"][-1] = [3.0e-5, 0.0]

    ordered = _ordered_closed_trim_paths(
        [
            np.asarray(record["uv"], dtype=float)
            for record in authority["trim_boundary_uv_paths"]
        ]
    )

    assert len(ordered) == 4


def test_source_boundary_samples_survive_nonclosing_uv_trim_without_differentials():
    authority = _quadratic_source_surface("source-open-differential-trim", 0.0)
    authority["trim_boundary_uv_paths"][-1]["uv"][-1] = [0.01, 0.0]

    samples = _source_boundary_samples(authority, np.eye(4))

    assert len(samples) == 4
    assert all(record["samples_xyz_mm"] for record in samples)
    assert all("surface_normal_samples" not in record for record in samples)
    assert all("differential_measurement_authority" not in record for record in samples)


def test_source_boundary_samples_prefer_exact_canonical_edge_over_face_uv_reprojection():
    authority = _quadratic_source_surface("source-exact-edge-authority", 0.0)
    exact_edge = [[10.0, 20.0, 30.0], [40.0, 50.0, 60.0]]
    authority["trim_boundary_uv_paths"][0]["canonical_points_xyz_mm"] = exact_edge

    samples = _source_boundary_samples(authority, np.eye(4))
    root = next(record for record in samples if record["boundary_path_id"] == "root")

    assert root["samples_xyz_mm"] == exact_edge


def test_trim_sampler_accepts_closed_triangular_source_patch():
    authority = _quadratic_source_surface("source-triangular-tip-patch", 3.0)
    authority["trim_boundary_uv_paths"] = [
        {"boundary_path_id": "root", "uv": [[0.0, 0.0], [1.0, 0.0]]},
        {"boundary_path_id": "diagonal", "uv": [[1.0, 0.0], [0.0, 1.0]]},
        {"boundary_path_id": "leading", "uv": [[0.0, 1.0], [0.0, 0.0]]},
    ]

    patches = _sample_authenticated_trimmed_surface_patches(
        authority,
        stream_sample_count=33,
        span_sample_count=17,
    )

    assert len(patches) == 3
    assert all(evidence["trim_boundary_path_count"] == 3 for _, evidence in patches)
    assert all(
        evidence["surface_quality"]["status"] == "PASS"
        for _, evidence in patches
    )
    assert all(
        evidence["edge_authority"]["u_end"]["boundary_kind"]
        == "internal_patch_edge"
        and evidence["edge_authority"]["v_end"]["boundary_kind"]
        == "internal_patch_edge"
        for _, evidence in patches
    )
    assert all(
        _single_surface_quality(sampled)["status"] == "PASS"
        for sampled, _ in patches
    )


def test_trim_polygon_quad_partition_handles_non_star_curved_boundary():
    authority = _quadratic_source_surface("source-concave-tip-patch", 3.0)
    authority["canonical_control_points_xyz_mm"] = [
        [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [[0.5, 0.0, 0.0], [0.5, 1.0, 0.0]],
        [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
    ]
    paths = [
        np.asarray([[0.0, 0.0], [1.0, 0.0]]),
        np.asarray([[1.0, 0.0], [0.8, 0.2], [0.25, 0.25], [0.0, 1.0]]),
        np.asarray([[0.0, 1.0], [0.0, 0.0]]),
    ]
    records = [
        {
            "boundary_path_id": f"boundary-{index}",
            "source_edge_id": f"source-edge-{index}",
        }
        for index in range(len(paths))
    ]

    patches = _sample_trim_polygon_quad_partition(
        authority,
        paths,
        records=records,
        row_count=9,
        column_count=17,
    )

    assert len(patches) > 3
    assert all(
        evidence["method"]
        == "authenticated_trim_polygon_ear_clip_quad_partition"
        for _, evidence in patches
    )
    assert all(
        evidence["boundary_chord_error_max_mm"]
        <= evidence["boundary_chord_tolerance_mm"]
        for _, evidence in patches
    )
    edge_authorities = [
        edge
        for _, evidence in patches
        for edge in evidence["edge_authority"].values()
    ]
    assert any(
        edge["boundary_kind"] == "internal_patch_edge"
        for edge in edge_authorities
    )
    assert {
        edge["source_edge_id"]
        for edge in edge_authorities
        if edge["boundary_kind"] == "source_trim"
    } == {f"source-edge-{index}" for index in range(len(paths))}
    assert all(
        edge["boundary_kind"]
        in {"source_trim", "internal_patch_edge"}
        for edge in edge_authorities
    )
    assert all(
        _single_surface_quality(sampled)["status"] == "PASS"
        for sampled, _ in patches
    )


def test_exact_patch_instances_reuse_sample_quality_without_copying_stale_geometry(
    monkeypatch,
):
    stale_grid = [
        [[float(row), float(column), 9.0] for column in range(97)]
        for row in range(49)
    ]
    surface = {
        "id": "root",
        "role": "root_to_hub_attachment",
        "face_family": "blade_root",
        "blade_class": "main",
        "blade_pair_index": 0,
        "uv_grid": stale_grid,
        "edge_samples": {"stale": stale_grid[0]},
        "v1_1_tip_quality": {"status": "STALE"},
    }
    sampled = [
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]],
    ]
    sampling = {
        "surface_quality": {"status": "PASS", "foldover_count": 0},
        "edge_authority": {},
    }
    patches = [
        (0, index, {"source_face_id": "source-face"}, sampled, sampling, [])
        for index in range(2)
    ]

    def unexpected_quality_recalculation(*_args, **_kwargs):
        raise AssertionError("rigid instances must reuse sampled patch quality")

    monkeypatch.setattr(
        surfaces_module,
        "_authenticated_trim_surface_quality",
        unexpected_quality_recalculation,
    )
    surfaces = [surface]

    replaced = _replace_exact_trimmed_patch_surfaces(
        surfaces,
        surface,
        (),
        np.eye(4),
        construction="test_exact_patch",
        quality_key="v1_1_root_quality",
        sampled_patches=patches,
    )

    assert replaced == ["root", "root_source_patch_01"]
    assert len(surfaces) == 2
    assert all(item["uv_grid"] == sampled for item in surfaces)
    assert all("v1_1_tip_quality" not in item for item in surfaces)
    assert all(
        item["v1_1_root_quality"]["rigid_transform_invariant_reuse"] is True
        for item in surfaces
    )


def test_multi_edge_trim_partition_preserves_every_source_boundary():
    authority = _quadratic_source_surface("source-five-edge-root", 0.0)
    authority["trim_boundary_uv_paths"] = [
        {"boundary_path_id": "edge-0", "source_edge_id": "edge-0", "uv": [[0.0, 0.0], [0.55, 0.0]]},
        {"boundary_path_id": "edge-1", "source_edge_id": "edge-1", "uv": [[0.55, 0.0], [1.0, 0.0]]},
        {"boundary_path_id": "edge-2", "source_edge_id": "edge-2", "uv": [[1.0, 0.0], [1.0, 1.0]]},
        {"boundary_path_id": "edge-3", "source_edge_id": "edge-3", "uv": [[1.0, 1.0], [0.0, 1.0]]},
        {"boundary_path_id": "edge-4", "source_edge_id": "edge-4", "uv": [[0.0, 1.0], [0.0, 0.0]]},
    ]

    patches = _sample_authenticated_trimmed_surface_patches(
        authority,
        stream_sample_count=33,
        span_sample_count=17,
    )

    represented = {
        edge_id
        for _grid, evidence in patches
        for edge_id in evidence.get("source_boundary_edge_ids", ())
    }
    assert represented == {f"edge-{index}" for index in range(5)}
    assert len(patches) == 1
    assert all(
        evidence["method"] == "authenticated_monotone_trim_scanline_grid"
        for _grid, evidence in patches
    )


def test_trim_path_order_uses_step_vertex_tolerance_not_uv_endpoint_equality():
    authority = {
        "source_face_id": "source-periodic-seam-face",
        "trim_boundary_uv_paths": [
            {
                "boundary_path_id": "edge-0",
                "uv": [[0.0, 0.0], [1.0, 0.0]],
                "canonical_points_xyz_mm": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                "source_vertex_tolerances_mm": [0.007, 0.007],
            },
            {
                "boundary_path_id": "edge-1",
                "uv": [[1.1, 0.0], [1.0, 1.0]],
                "canonical_points_xyz_mm": [[1.006, 0.0, 0.0], [1.0, 1.0, 0.0]],
                "source_vertex_tolerances_mm": [0.007, 0.007],
            },
            {
                "boundary_path_id": "edge-2",
                "uv": [[1.0, 1.0], [0.0, 1.0]],
                "canonical_points_xyz_mm": [[1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
                "source_vertex_tolerances_mm": [0.007, 0.007],
            },
            {
                "boundary_path_id": "edge-3",
                "uv": [[0.0, 1.0], [0.0, 0.0]],
                "canonical_points_xyz_mm": [[0.0, 1.0, 0.0], [0.0, 0.0, 0.0]],
                "source_vertex_tolerances_mm": [0.007, 0.007],
            },
        ],
    }
    paths = [
        np.asarray(record["uv"], dtype=float)
        for record in authority["trim_boundary_uv_paths"]
    ]

    ordered, records = _ordered_trim_paths_with_records(authority, paths)

    assert len(ordered) == 4
    assert [record["boundary_path_id"] for record in records] == [
        "edge-0",
        "edge-1",
        "edge-2",
        "edge-3",
    ]


def test_attachment_topology_contract_matches_different_edge_sample_counts():
    surfaces = [
        {
            "id": "pressure",
            "role": "blade_pressure",
            "blade_class": "main",
            "blade_pair_index": 0,
            "edge_samples": {"root": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]},
            "edge_authority": {
                "root": {
                    "boundary_kind": "source_trim",
                    "source_edge_id": "shared-root-edge",
                }
            },
        },
        {
            "id": "root",
            "role": "root_to_hub_attachment",
            "blade_class": "main",
            "blade_pair_index": 0,
            "edge_samples": {
                "u_start": [
                    [1.0, 0.0, 0.0],
                    [0.75, 0.0, 0.0],
                    [0.5, 0.0, 0.0],
                    [0.25, 0.0, 0.0],
                    [0.0, 0.0, 0.0],
                ]
            },
            "edge_authority": {
                "u_start": {
                    "boundary_kind": "source_trim",
                    "source_edge_id": "shared-root-edge",
                }
            },
        },
    ]

    contract = _attachment_topology_contract(surfaces, tolerance_mm=1.0e-8)

    assert contract["status"] == "PASS"
    assert contract["matched_shared_edge_count"] == 1
    assert contract["max_coordinate_gap_mm"] <= 1.0e-12
    assert contract["unowned_blade_side_source_boundary_count"] == 0


def test_attachment_topology_contract_measures_source_boundary_differentials():
    boundary = [[0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [1.0, 0.0, 0.0]]
    normals = [[0.0, 0.0, 1.0]] * 3
    curvature = [0.25, 0.25, 0.25]
    surfaces = []
    for surface_id, role, points in (
        ("pressure", "blade_pressure", boundary),
        ("root", "root_to_hub_attachment", list(reversed(boundary))),
    ):
        samples = list(reversed(normals)) if surface_id == "root" else normals
        curvatures = list(reversed(curvature)) if surface_id == "root" else curvature
        surfaces.append(
            {
                "id": surface_id,
                "role": role,
                "blade_class": "main",
                "blade_pair_index": 0,
                "source_boundary_samples": [
                    {
                        "source_edge_id": "shared-root-edge",
                        "boundary_path_id": "root",
                        "samples_xyz_mm": points,
                        "surface_normal_samples": samples,
                        "transverse_normal_curvature_samples_per_mm": curvatures,
                    }
                ],
            }
        )

    contract = _attachment_topology_contract(surfaces, tolerance_mm=1.0e-8)

    assert contract["status"] == "PASS"
    assert contract["g1_measurement_status"] == "PASS"
    assert contract["g2_measurement_status"] == "PASS"
    assert contract["regular_edge_continuity_status"] == "PASS"
    assert contract["corner_coupling_status"] == "PASS"
    assert contract["continuity_status"] == "PASS"
    assert contract["measured_differential_shared_edge_count"] == 1
    assert contract["max_normal_angle_deg"] <= 1.0e-9
    assert contract["max_curvature_proxy_mismatch"] <= 1.0e-9


def test_attachment_topology_contract_rejects_unowned_side_source_boundary():
    contract = _attachment_topology_contract(
        [
            {
                "id": "pressure",
                "role": "blade_pressure",
                "blade_class": "main",
                "blade_pair_index": 0,
                "source_boundary_samples": [
                    {
                        "source_edge_id": "missing-root-owner",
                        "boundary_path_id": "root",
                        "samples_xyz_mm": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                    }
                ],
            }
        ],
        tolerance_mm=1.0e-8,
    )

    assert contract["status"] == "FAIL"
    assert contract["unowned_blade_side_source_boundary_count"] == 1


def test_attachment_topology_groups_periodic_instances_before_geometry_matching(
    monkeypatch,
):
    surfaces = [
        {
            "id": f"pressure-{index}",
            "role": "blade_pressure",
            "blade_class": "main",
            "blade_pair_index": index,
            "source_boundary_samples": [
                {
                    "source_edge_id": f"source-edge-{index}",
                    "boundary_path_id": "root",
                    "samples_xyz_mm": [
                        [float(index), 0.0, 0.0],
                        [float(index), 1.0, 0.0],
                    ],
                }
            ],
        }
        for index in range(1000)
    ]
    call_count = 0
    original = surfaces_module._arc_length_boundary_gap

    def counted_gap(first, second, *, sample_count=65):
        nonlocal call_count
        call_count += 1
        return original(first, second, sample_count=sample_count)

    monkeypatch.setattr(
        surfaces_module,
        "_arc_length_boundary_gap",
        counted_gap,
    )

    contract = _attachment_topology_contract(
        surfaces,
        tolerance_mm=1.0e-8,
    )

    assert contract["candidate_group_count"] == 1000
    assert contract["geometric_candidate_pair_count"] == 0
    assert call_count == 0


def test_attachment_continuity_separates_edge_interior_from_corner_endpoints():
    boundary = [[float(index), 0.0, 0.0] for index in range(9)]
    first_normals = [[0.0, 0.0, 1.0]] * 9
    second_normals = copy.deepcopy(first_normals)
    second_normals[0] = [1.0, 0.0, 0.0]
    second_normals[-1] = [1.0, 0.0, 0.0]
    surfaces = []
    for surface_id, role, points, normals in (
        ("pressure", "blade_pressure", boundary, first_normals),
        (
            "root",
            "root_to_hub_attachment",
            list(reversed(boundary)),
            list(reversed(second_normals)),
        ),
    ):
        surfaces.append(
            {
                "id": surface_id,
                "role": role,
                "blade_class": "main",
                "blade_pair_index": 0,
                "source_boundary_samples": [
                    {
                        "source_edge_id": "shared-root-edge",
                        "boundary_path_id": "root",
                        "samples_xyz_mm": points,
                        "surface_normal_samples": normals,
                        "transverse_normal_curvature_samples_per_mm": [0.25] * 9,
                    }
                ],
            }
        )

    contract = _attachment_topology_contract(surfaces, tolerance_mm=1.0e-8)

    assert contract["status"] == "PASS"
    assert contract["g1_measurement_status"] == "PASS"
    assert contract["regular_edge_continuity_status"] == "PASS"
    assert contract["corner_g1_measurement_status"] == "MEASURED_DISCONTINUOUS"
    assert contract["corner_coupling_status"] == "FAIL"
    assert contract["continuity_status"] == "FAIL"
    assert contract["max_normal_angle_deg"] <= 1.0e-9
    assert contract["max_endpoint_corner_normal_angle_deg"] == pytest.approx(90.0)


def test_attachment_topology_contract_fails_closed_when_all_source_ids_are_missing():
    contract = _attachment_topology_contract(
        [
            {
                "id": "pressure",
                "role": "blade_pressure",
                "blade_class": "main",
                "blade_pair_index": 0,
                "source_boundary_samples": [
                    {
                        "boundary_path_id": "root",
                        "samples_xyz_mm": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                    }
                ],
            }
        ],
        tolerance_mm=1.0e-8,
    )

    assert contract["status"] == "FAIL"
    assert contract["reason"] == "source_edge_identity_incomplete"
    assert contract["missing_source_edge_identity_count"] == 1


def test_attachment_topology_contract_fails_closed_on_partial_source_identity():
    boundary = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    contract = _attachment_topology_contract(
        [
            {
                "id": "pressure",
                "role": "blade_pressure",
                "blade_class": "main",
                "blade_pair_index": 0,
                "source_boundary_samples": [
                    {
                        "source_edge_id": "shared-root",
                        "boundary_path_id": "root",
                        "samples_xyz_mm": boundary,
                    },
                    {
                        "boundary_path_id": "unidentified-tip",
                        "samples_xyz_mm": boundary,
                    },
                ],
            },
            {
                "id": "root",
                "role": "root_to_hub_attachment",
                "blade_class": "main",
                "blade_pair_index": 0,
                "source_boundary_samples": [
                    {
                        "source_edge_id": "shared-root",
                        "boundary_path_id": "root",
                        "samples_xyz_mm": list(reversed(boundary)),
                    }
                ],
            },
        ],
        tolerance_mm=1.0e-8,
    )

    assert contract["status"] == "FAIL"
    assert contract["reason"] == "source_edge_identity_incomplete"
    assert contract["missing_source_edge_identity_count"] == 1


@pytest.mark.parametrize(
    "seam_kind,source_edge_id",
    [
        ("degenerate_trim_seam", None),
        ("periodic_parameter_seam", "periodic-seam-edge"),
    ],
)
def test_source_boundary_samples_exclude_face_local_trim_seam_from_c0_contract(
    seam_kind, source_edge_id
):
    authority = _quadratic_source_surface("source-root", 0.0)
    authority["trim_boundary_uv_paths"] = [
        {
            "boundary_path_id": "material-0",
            "source_edge_id": "edge-0",
            "topology_boundary_kind": "material_shared_edge",
            "uv": [[0.0, 0.0], [1.0, 0.0]],
            "canonical_points_xyz_mm": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        },
        {
            "boundary_path_id": "material-1",
            "source_edge_id": "edge-1",
            "topology_boundary_kind": "material_shared_edge",
            "uv": [[1.0, 0.0], [1.0, 1.0]],
            "canonical_points_xyz_mm": [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]],
        },
        {
            "boundary_path_id": "material-2",
            "source_edge_id": "edge-2",
            "topology_boundary_kind": "material_shared_edge",
            "uv": [[1.0, 1.0], [0.0, 1.0]],
            "canonical_points_xyz_mm": [[1.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
        },
        {
            "boundary_path_id": "face-local-pole",
            **({"source_edge_id": source_edge_id} if source_edge_id else {}),
            "topology_boundary_kind": seam_kind,
            "uv": [[0.0, 1.0], [0.0, 0.0]],
            "canonical_points_xyz_mm": [[0.0, 1.0, 0.0], [0.0, 0.0, 0.0]],
        },
    ]

    records = _source_boundary_samples(authority, np.eye(4))

    assert {record["source_edge_id"] for record in records} == {
        "edge-0",
        "edge-1",
        "edge-2",
    }
    assert all(
        record["topology_boundary_kind"] == "material_shared_edge"
        for record in records
    )


def test_continuity_failure_is_not_cleared_by_c0_only_replacement():
    graph = {
        "transition_failures": [
            {
                "surface_id": "tip",
                "reason": "v1_1_tip_continuity_failed",
            }
        ]
    }

    _remove_superseded_surface_failures(
        graph,
        {"tip"},
        replacement_topology={"status": "PASS", "continuity_status": "FAIL"},
    )

    assert graph["transition_failures"] == [
        {"surface_id": "tip", "reason": "v1_1_tip_continuity_failed"}
    ]


def test_exact_patch_sampling_is_reused_across_periodic_instances(monkeypatch):
    mapping = _mapping()
    authority = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["active_span_authority"]
    authority["tip_surface_patches"] = [
        _quadratic_source_surface("source-tip-patch", 9.0)
    ]
    calls = 0
    original = _sample_authenticated_trimmed_surface_patches

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        "part_rule_synthesis.impeller_v11_6_section_curve_surfaces._sample_authenticated_trimmed_surface_patches",
        counted,
    )

    replace_blade_surfaces_with_direct_section_curves(
        _graph(with_attachments=True),
        mapping,
        span_sample_count=9,
        curve_sample_count=17,
    )

    assert calls == 1


def test_open_tip_rejects_mismatched_side_sampling_with_stable_reason():
    grids = {
        "side_a": [[[float(index), 0.0, 0.0] for index in range(5)]],
        "side_b": [[[float(index), 1.0, 0.0] for index in range(3)]],
        "leading_edge": [[[0.0, 1.0, 0.0], [0.0, 0.0, 0.0]]],
        "trailing_edge": [[[4.0, 0.0, 0.0], [2.0, 1.0, 0.0]]],
    }

    with pytest.raises(DirectSectionSurfaceError) as caught:
        _coons_tip_grid(grids, 0)

    assert caught.value.reason == "v116_direct_curve_attachment_invalid"
    assert caught.value.details == {
        "pressure_boundary_sample_count": 5,
        "suction_boundary_sample_count": 3,
    }


def test_direct_root_attachment_keeps_retained_boundary_as_explicit_evidence_only():
    mapping = _mapping()
    authority = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["active_span_authority"]
    authority["retained_root_boundary_points_rz_mm"] = [
        [10.0, -0.5],
        [15.0, 0.5],
        [20.2, 1.5],
    ]
    graph, _manifest = replace_blade_surfaces_with_direct_section_curves(
        _graph(with_attachments=True),
        mapping,
        span_sample_count=9,
        curve_sample_count=17,
    )

    root = _surface(graph, 0, "root_to_hub_attachment")
    assert root["source"]["retained_boundary_authority"] == (
        "source_retained_blade_boundary_support_envelope"
    )
    assert root["source"]["retained_boundary_geometry_usage"] == (
        "evidence_only_pending_role_resolved_closed_boundary"
    )


def test_direct_surface_rejects_a_reversed_authoritative_station_row():
    mapping = _mapping()
    station = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["stations"][1]
    station["curves"]["side_a"]["canonical_points_xyz_mm"].reverse()

    with pytest.raises(DirectSectionSurfaceError) as caught:
        replace_blade_surfaces_with_direct_section_curves(
            _graph(), mapping, span_sample_count=9, curve_sample_count=17
        )

    assert caught.value.reason == "v116_direct_curve_surface_quality_failed"
    assert (
        caught.value.details["row_reversal_count"] > 0
        or caught.value.details["normal_flip_count"] > 0
        or caught.value.details["shared_boundary_orientation_mismatch_count"] > 0
    )


def test_sharp_shared_seam_quality_excludes_nonmaterial_endpoint_bridges():
    mapping = _mapping()
    stations = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["stations"]
    for station in stations:
        station["closure_classification"] = "sharp_shared_seam"

    graph, manifest = replace_blade_surfaces_with_direct_section_curves(
        _graph(), mapping, span_sample_count=9, curve_sample_count=17
    )

    quality = manifest["populations"][0]["surface_quality"]
    assert set(quality["role_quality"]) == {"side_a", "side_b"}
    assert quality["status"] == "PASS"
    assert _surface(graph, 0, "blade_leading_edge")["material"] is False
    assert _surface(graph, 0, "blade_trailing_edge")["material"] is False


def test_mixed_endpoint_measurements_use_authenticated_shared_trim_topology():
    mapping = _mapping()
    stations = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["stations"]
    for index, station in enumerate(stations):
        station["closure_classification"] = (
            "endpoint_witness_bridge_review_only"
            if index == 0
            else "sharp_shared_seam"
        )
        authority = _quadratic_source_surface("source-pressure-face", 0.0)
        station["curves"]["side_a"]["source_face_surface"] = authority
        station["curves"]["side_b"]["source_face_surface"] = copy.deepcopy(
            authority
        )

    assert _closure_mode(stations) == "sharp_shared_seam"


def test_mixed_endpoint_measurements_without_shared_trim_topology_fail():
    mapping = _mapping()
    stations = mapping["section_provenance"]["direct_section_curve_network"][
        "populations"
    ]["main"]["stations"]
    for index, station in enumerate(stations):
        station["closure_classification"] = (
            "endpoint_witness_bridge_review_only"
            if index == 0
            else "sharp_shared_seam"
        )
        station["curves"]["side_a"]["source_face_surface"] = (
            _quadratic_source_surface("source-pressure-face", 0.0)
        )
        station["curves"]["side_b"]["source_face_surface"] = (
            _quadratic_source_surface("source-suction-face", 2.0)
        )

    with pytest.raises(DirectSectionSurfaceError) as caught:
        _closure_mode(stations)

    assert caught.value.reason == "v116_direct_curve_closure_inconsistent"
    assert len(caught.value.details["station_modes"]) == len(stations)


def test_direct_attachment_surfaces_publish_passing_quality_evidence():
    graph, _manifest = replace_blade_surfaces_with_direct_section_curves(
        _graph(with_attachments=True),
        _mapping(),
        span_sample_count=9,
        curve_sample_count=17,
    )

    for role in ("root_to_hub_attachment", "open_tip_dome"):
        quality = _surface(graph, 0, role)["source"]["surface_quality"]
        assert quality["status"] == "PASS"
        assert quality["row_reversal_count"] == 0
        assert quality["normal_flip_count"] == 0

    root_quality = _surface(graph, 0, "root_to_hub_attachment")[
        "v1_1_root_quality"
    ]
    assert root_quality["status"] == "PASS"
    assert root_quality["material_side_status"] == "PASS"
    assert root_quality["support_to_blade_separation_min_mm"] > 0.0
    tip_quality = _surface(graph, 0, "open_tip_dome")["v1_1_tip_quality"]
    assert tip_quality["status"] == "PASS"
    assert tip_quality["tip_area_ratio"] == pytest.approx(1.0)


def test_direct_replacement_preserves_failures_when_strict_topology_is_not_applicable():
    source = _graph(with_attachments=True)
    source["transition_failures"] = [
        {
            "reason": "v1_1_root_attachment_failed",
            "surface_id": "blade_0_root_to_hub_attachment",
        },
        {
            "reason": "unrelated_failure",
            "surface_id": "unrelated_surface",
        },
    ]

    graph, _manifest = replace_blade_surfaces_with_direct_section_curves(
        source,
        _mapping(),
        span_sample_count=9,
        curve_sample_count=17,
    )

    assert graph["transition_failures"] == [
        {
            "reason": "v1_1_root_attachment_failed",
            "surface_id": "blade_0_root_to_hub_attachment",
        },
        {
            "reason": "unrelated_failure",
            "surface_id": "unrelated_surface",
        }
    ]
    assert graph["geometry_generation_status"] == "FAIL"


def test_c0_pass_clears_superseded_non_continuity_failure():
    graph = {
        "transition_failures": [
            {"surface_id": "root", "reason": "v1_1_root_attachment_failed"}
        ]
    }

    _remove_superseded_surface_failures(
        graph,
        {"root"},
        replacement_topology={"status": "PASS", "continuity_status": "FAIL"},
    )

    assert graph["transition_failures"] == []


def test_common_z_gate_rejects_unexplained_hub_blade_root_cutoff():
    graph = {
        "surfaces": [
            _cutoff_surface("hub_revolve_surface", "hub", "hub", 5.0),
            _cutoff_surface("blade_pressure", "blade_pressure", "blade", 5.0),
            _cutoff_surface(
                "root_attachment",
                "root_to_hub_attachment",
                "root",
                5.0,
            ),
        ]
    }
    endpoint_witnesses = {
        "source_tolerance_mm": 0.01,
        "blade_leading_boundary": {"canonical_z_range_mm": [1.0, 9.0]},
    }

    diagnostic = _common_z_boundary_diagnostic(
        graph,
        endpoint_witnesses=endpoint_witnesses,
    )

    assert diagnostic["status"] == "FAIL"
    assert diagnostic["unexplained_common_z_clusters"][0]["categories"] == [
        "blade_side",
        "hub",
        "root_attachment",
    ]


def test_common_z_gate_accepts_a_source_witnessed_planar_leading_boundary():
    graph = {
        "surfaces": [
            _cutoff_surface("hub_revolve_surface", "hub", "hub", 5.0),
            _cutoff_surface("blade_pressure", "blade_pressure", "blade", 5.0),
            _cutoff_surface(
                "root_attachment",
                "root_to_hub_attachment",
                "root",
                5.0,
            ),
        ]
    }

    diagnostic = _common_z_boundary_diagnostic(
        graph,
        endpoint_witnesses={
            "source_tolerance_mm": 0.01,
            "blade_leading_boundary": {"canonical_z_range_mm": [5.0, 5.0]},
        },
    )

    assert diagnostic["status"] == "PASS"
    assert any(
        cluster["source_explanation"]
        == "authenticated_source_blade_leading_boundary_is_planar"
        for cluster in diagnostic["clusters"]
    )


def _mapping():
    stations = []
    for h in (0.0, 0.5, 1.0):
        stations.append(
            {
                "contract_id": "impeller_v1_1_6_direct_section_curve_network_r16_1",
                "active_h": h,
                "support_profile_rz_mm": [
                    [10.0, 5.0 * h],
                    [15.0, 5.0 * h + 1.0],
                    [20.2, 5.0 * h + 2.0],
                ],
                "curves": {
                    role: {
                        "canonical_points_xyz_mm": _curve_points(h, role),
                        "u": [0.0, 0.5, 1.0],
                        **(
                            {"s_physical_mm": [point[0] for point in _curve_points(h, role)]}
                            if role in {"side_a", "side_b"}
                            else {}
                        ),
                    }
                    for role in ("side_a", "side_b", "leading_edge", "trailing_edge")
                },
            }
        )
    return {
        "section_provenance": {
            "direct_section_curve_network": {
                "contract_id": "impeller_v1_1_6_direct_section_curve_network_r16_1",
                "status": "PASS",
                "construction_usage": "step_reconstruction_only",
                "populations": {
                    "main": {
                        "population": "main",
                        "stations": stations,
                        "active_span_authority": {
                            "hub_points_rz_mm": [[10.0, -1.0], [15.0, 0.0], [20.2, 1.0]],
                            "tip_points_rz_mm": [[10.0, 6.0], [15.0, 7.0], [20.2, 8.0]],
                        },
                    }
                },
            }
        },
        "periodic_provenance": {
            "pattern_population_evidence": {
                "populations": [
                    {
                        "classification": "main",
                        "instances": [
                            {"lattice_index": 0, "transform_from_representative": _rotation(0.0)},
                            {"lattice_index": 1, "transform_from_representative": _rotation(180.0)},
                        ],
                    }
                ]
            }
        },
    }


def _curve_points(h, role):
    z = 5.0 * h
    if role == "side_a":
        return [[10.0, -1.0, z], [15.0, -1.5 - h, z + 1.0], [20.0, -1.0, z + 2.0]]
    if role == "side_b":
        return [[12.55, 1.0, z], [16.0, 1.4 + h, z + 1.0], [20.2, 1.0, z + 2.0]]
    if role == "leading_edge":
        return [[12.55, 1.0, z], [11.2, 0.0, z], [10.0, -1.0, z]]
    return [[20.0, -1.0, z + 2.0], [20.4, 0.0, z + 2.0], [20.2, 1.0, z + 2.0]]


def _graph(*, with_attachments=False):
    surfaces = []
    for index in (0, 1):
        for role in (
            "blade_pressure",
            "blade_suction",
            "blade_leading_edge",
            "blade_trailing_edge",
        ):
            surfaces.append(
                {
                    "id": f"blade_{index}_{role}",
                    "feature_id": f"blade_{index}",
                    "blade_class": "main",
                    "blade_pair_index": index,
                    "role": role,
                    "face_family": role,
                    "uv_grid": [[[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]], [[1.0, 0.0, 1.0], [2.0, 0.0, 1.0]]],
                    "edge_samples": {},
                }
            )
        if with_attachments:
            for role, face_family in (
                ("root_to_hub_attachment", "blade_root"),
                ("open_tip_dome", "blade_tip"),
            ):
                surfaces.append(
                    {
                        "id": f"blade_{index}_{role}",
                        "feature_id": f"blade_{index}",
                        "blade_class": "main",
                        "blade_pair_index": index,
                        "role": role,
                        "face_family": face_family,
                        "uv_grid": [[[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]], [[1.0, 0.0, 1.0], [2.0, 0.0, 1.0]]],
                        "edge_samples": {},
                    }
                )
    return {"surfaces": surfaces, "topology_graph": {}}


def _surface(graph, index, role):
    return next(
        surface
        for surface in graph["surfaces"]
        if surface.get("blade_pair_index") == index and surface.get("role") == role
    )


def _assert_parameter_inspection_matches_final_surfaces(graph):
    contract = graph["parameter_inspection"]
    surface_ids = {str(surface["id"]) for surface in graph["surfaces"]}
    expected_generation_id = parameter_inspection_generation_id(graph)
    assert graph["generation_id"] == expected_generation_id
    assert contract["generation_id"] == expected_generation_id
    assert set(contract["surface_references"]) == surface_ids


def _root_anchor_surface(blade_index, authority_index, point):
    return {
        "id": (
            f"blade_{blade_index}_root_attachment_surface_"
            f"source_patch_{authority_index:02d}"
        ),
        "blade_index": blade_index,
        "role": "root_to_hub_attachment",
        "source": {
            "source_authority_index": authority_index,
            "trim_subpatch_index": 0,
        },
        "uv_grid": [[[point[0], point[1], 0.0]], [point]],
    }


def _cutoff_surface(surface_id, role, blade_class, z):
    return {
        "id": surface_id,
        "role": role,
        "blade_class": blade_class,
        "uv_grid": [
            [[1.0, 0.0, z], [2.0, 0.0, z]],
            [[1.0, 1.0, z], [2.0, 1.0, z + 1.0]],
        ],
    }


def _rotation(angle_deg):
    angle = math.radians(angle_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        [cosine, -sine, 0.0, 0.0],
        [sine, cosine, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _quadratic_source_surface(face_id, y_offset):
    return {
        "source_face_id": face_id,
        "u_degree": 2,
        "v_degree": 1,
        "u_knots": [0.0, 1.0],
        "v_knots": [0.0, 1.0],
        "u_multiplicities": [3, 3],
        "v_multiplicities": [2, 2],
        "canonical_control_points_xyz_mm": [
            [[0.0, y_offset, 0.0], [0.0, y_offset, 1.0]],
            [[5.0, y_offset, 0.0], [5.0, y_offset, 1.0]],
            [[10.0, 10.0 + y_offset, 0.0], [10.0, 10.0 + y_offset, 1.0]],
        ],
        "weights": [[1.0, 1.0], [1.0, 1.0], [1.0, 1.0]],
        "trim_boundary_uv_paths": [
            {"boundary_path_id": "root", "uv": [[0.0, 0.0], [1.0, 0.0]]},
            {"boundary_path_id": "trailing", "uv": [[1.0, 0.0], [1.0, 1.0]]},
            {"boundary_path_id": "tip", "uv": [[1.0, 1.0], [0.0, 1.0]]},
            {
                "boundary_path_id": "leading",
                "uv": [[5.0e-7, 1.0], [-5.0e-7, 0.5], [4.0e-7, 0.0]],
            },
        ],
    }


def _rotate_grid(grid, angle_deg):
    matrix = np.asarray(_rotation(angle_deg), dtype=float)
    points = np.asarray(grid, dtype=float)
    flat = points.reshape(-1, 3)
    homogeneous = np.column_stack([flat, np.ones(len(flat))])
    return (matrix @ homogeneous.T).T[:, :3].reshape(points.shape)
