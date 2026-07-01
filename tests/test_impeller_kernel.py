from part_rule_synthesis.impeller_kernel import build_impeller_geometry


def test_impeller_kernel_is_deterministic_and_uses_one_surface_for_uv_lines():
    parameters = {
        "blade_count": 6,
        "inlet_radius_mm": 320.0,
        "exit_radius_mm": 980.0,
        "inlet_blade_height_mm": 260.0,
        "outlet_blade_height_mm": 180.0,
        "inlet_blade_angle_deg": 24.0,
        "outlet_blade_angle_deg": 42.0,
        "blade_thickness_mm": 36.0,
        "blade_curve_gain": 1.4,
        "hub_curve_height_mm": 220.0,
    }
    facets = {
        "flow_topology": "mixed",
        "shroud_topology": "closed",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    first = build_impeller_geometry(parameters, facets)
    second = build_impeller_geometry(parameters, facets)

    assert first == second
    assert first["kernel"]["kind"] == "meridional_beta_thickness_kernel"
    assert first["kernel"]["uv_sampling"] == {"u_count": 9, "v_count": 5}
    first_blade = first["sampled_blades"][0]["mean_surface"]
    assert first["construction_lines"]["blade_u"][0]["points"] == first_blade[0]
    assert first["construction_lines"]["blade_v"][0]["points"] == [row[0] for row in first_blade]
    assert first["kernel"]["beta_field"]["degree"] == 3
    assert first["kernel"]["beta_field"]["control_points_deg"][0] == 24.0
    assert first["kernel"]["beta_field"]["control_points_deg"][-1] == 42.0


def test_impeller_kernel_marks_recessed_vortex_as_free_passage_geometry():
    parameters = {
        "blade_count": 8,
        "inlet_radius_mm": 260.0,
        "exit_radius_mm": 900.0,
        "inlet_blade_height_mm": 180.0,
        "outlet_blade_height_mm": 130.0,
        "inlet_blade_angle_deg": 18.0,
        "outlet_blade_angle_deg": 70.0,
        "blade_thickness_mm": 42.0,
        "blade_curve_gain": 1.7,
        "hub_curve_height_mm": 120.0,
    }
    facets = {
        "flow_topology": "radial",
        "shroud_topology": "open",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "forward_curved",
        "working_domain": "pump",
        "passage_topology": "recessed_vortex",
    }

    geometry = build_impeller_geometry(parameters, facets)

    assert geometry["kernel"]["passage_model"] == {
        "type": "recessed_vortex",
        "throughflow_bladed_channel": False,
        "free_passage_cavity": True,
    }
    assert "recessed_vortex_impeller_proxy" in geometry["cad_features"]
    assert "throughflow_channel_proxy" not in geometry["cad_features"]
    assert geometry["construction_lines"]["passage"]
    assert max(point[2] for line in geometry["construction_lines"]["passage"] for point in line["points"]) > 0.0


def test_impeller_kernel_builds_surface_graph_with_hub_revolve_and_connector_surfaces():
    parameters = {
        "blade_count": 6,
        "inlet_radius_mm": 320.0,
        "exit_radius_mm": 980.0,
        "inlet_blade_height_mm": 260.0,
        "outlet_blade_height_mm": 180.0,
        "inlet_blade_angle_deg": 24.0,
        "outlet_blade_angle_deg": 42.0,
        "blade_thickness_mm": 36.0,
        "blade_curve_gain": 1.4,
        "hub_curve_height_mm": 220.0,
    }
    facets = {
        "flow_topology": "mixed",
        "shroud_topology": "closed",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    geometry = build_impeller_geometry(parameters, facets)
    graph = geometry["surface_graph"]
    surfaces = {surface["id"]: surface for surface in graph["surfaces"]}

    assert surfaces["hub_revolve_surface"]["kind"] == "nurbs_revolve_surface"
    assert surfaces["hub_revolve_surface"]["profile"]["kind"] == "nurbs_curve"
    assert surfaces["hub_revolve_surface"]["profile"]["degree"] == 3
    assert len(surfaces["hub_revolve_surface"]["profile"]["control_points"]) >= 4
    assert len(surfaces["hub_revolve_surface"]["profile"]["weights"]) == len(
        surfaces["hub_revolve_surface"]["profile"]["control_points"]
    )
    assert "blade_0_pressure_surface" in surfaces
    assert "blade_0_suction_surface" in surfaces
    assert "blade_0_root_fillet_surface" in surfaces
    assert "blade_0_leading_edge_fillet_surface" in surfaces
    assert "blade_0_trailing_edge_fillet_surface" in surfaces
    assert "blade_0_tip_surface" in surfaces
    assert any(
        set(edge["surfaces"]) == {"hub_revolve_surface", "blade_0_root_fillet_surface"}
        for edge in graph["edges"]
    )
    assert any(
        set(edge["surfaces"]) == {"blade_0_pressure_surface", "blade_0_leading_edge_fillet_surface"}
        for edge in graph["edges"]
    )
    uv_surface_ids = {line["surface_id"] for line in geometry["construction_lines"]["surface_uv"]}
    assert set(surfaces).issubset(uv_surface_ids)


def test_impeller_kernel_reports_geometry_and_topology_validity():
    parameters = {
        "blade_count": 7,
        "inlet_radius_mm": 420.2,
        "exit_radius_mm": 1400.65,
        "inlet_blade_height_mm": 394.0,
        "outlet_blade_height_mm": 251.0,
        "inlet_blade_angle_deg": 17.47,
        "outlet_blade_angle_deg": 21.19,
        "blade_thickness_mm": 56.0,
        "blade_curve_gain": 1.0,
        "hub_curve_height_mm": 160.0,
    }
    facets = {
        "flow_topology": "radial",
        "shroud_topology": "open",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    geometry = build_impeller_geometry(parameters, facets)
    validity = geometry["validity"]

    assert validity["status"] == "PASS"
    assert {check["name"] for check in validity["geometry_checks"]}.issuperset(
        {"positive_radii", "finite_surface_points", "non_degenerate_surface_boundaries", "hub_profile_monotonic"}
    )
    assert all(check["status"] == "PASS" for check in validity["geometry_checks"])
    assert {check["name"] for check in validity["topology_checks"]}.issuperset(
        {"blade_root_fillet_connects_hub", "edge_fillets_close_blade_surfaces", "every_surface_has_uv_lines"}
    )
    assert all(check["status"] == "PASS" for check in validity["topology_checks"])
    assert validity["engineering_checks"][0] == {
        "name": "engineering_rules",
        "status": "NOT_EVALUATED",
        "note": "CFD/FEA/DFMA checks are not implemented in this stage",
    }


def test_twisted_open_impeller_blade_boundaries_conform_to_hub_and_tip_surfaces():
    parameters = {
        "blade_count": 9,
        "inlet_radius_mm": 300.0,
        "exit_radius_mm": 1150.0,
        "inlet_blade_height_mm": 320.0,
        "outlet_blade_height_mm": 210.0,
        "inlet_blade_angle_deg": 19.0,
        "outlet_blade_angle_deg": 64.0,
        "blade_thickness_mm": 42.0,
        "blade_curve_gain": 2.3,
        "hub_curve_height_mm": 280.0,
        "hub_twist_deg": 32.0,
        "tip_twist_deg": 58.0,
        "hub_warp_mm": 42.0,
        "tip_warp_mm": 88.0,
    }
    facets = {
        "flow_topology": "mixed",
        "shroud_topology": "open",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    geometry = build_impeller_geometry(parameters, facets)
    first_blade = geometry["sampled_blades"][0]

    assert geometry["kernel"]["surface_fields"]["hub"]["twist_deg"] == 32.0
    assert geometry["kernel"]["surface_fields"]["tip"]["warp_mm"] == 88.0
    assert first_blade["mean_surface"][0][0] == first_blade["hub_boundary"][0]
    assert first_blade["mean_surface"][-1][0] == first_blade["hub_boundary"][-1]
    assert first_blade["mean_surface"][0][-1] == first_blade["tip_boundary"][0]
    assert first_blade["mean_surface"][-1][-1] == first_blade["tip_boundary"][-1]
    assert geometry["surface_graph"]["boundary_curves"]["blade_0_hub_boundary"] == first_blade["hub_boundary"]
    assert geometry["surface_graph"]["boundary_curves"]["blade_0_tip_boundary"] == first_blade["tip_boundary"]
    conformance = {
        check["name"]: check
        for check in geometry["validity"]["topology_checks"]
        if check["name"].endswith("_boundary_conformance")
    }
    assert conformance["blade_hub_boundary_conformance"]["status"] == "PASS"
    assert conformance["blade_tip_boundary_conformance"]["status"] == "PASS"
    assert conformance["blade_hub_boundary_conformance"]["max_distance_mm"] == 0.0
    assert conformance["blade_tip_boundary_conformance"]["max_distance_mm"] == 0.0


def test_twisted_closed_impeller_tip_boundary_conforms_to_shroud_surface():
    parameters = {
        "blade_count": 8,
        "inlet_radius_mm": 340.0,
        "exit_radius_mm": 1180.0,
        "inlet_blade_height_mm": 300.0,
        "outlet_blade_height_mm": 230.0,
        "inlet_blade_angle_deg": 22.0,
        "outlet_blade_angle_deg": 50.0,
        "blade_thickness_mm": 38.0,
        "blade_curve_gain": 2.0,
        "hub_curve_height_mm": 240.0,
        "hub_twist_deg": 24.0,
        "tip_twist_deg": 46.0,
        "hub_warp_mm": 36.0,
        "tip_warp_mm": 70.0,
    }
    facets = {
        "flow_topology": "mixed",
        "shroud_topology": "closed",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    geometry = build_impeller_geometry(parameters, facets)
    surfaces = {surface["id"]: surface for surface in geometry["surface_graph"]["surfaces"]}
    first_blade = geometry["sampled_blades"][0]

    assert surfaces["shroud_surface"]["kind"] == "warped_shroud_surface"
    assert surfaces["shroud_surface"]["uv_grid"][0][0] == first_blade["tip_boundary"][0]
    assert geometry["surface_graph"]["boundary_curves"]["blade_0_shroud_boundary"] == first_blade["tip_boundary"]
    assert any(
        set(edge["surfaces"]) == {"shroud_surface", "blade_0_tip_surface"}
        and edge["relation"] == "conformal_tip_boundary"
        for edge in geometry["surface_graph"]["edges"]
    )


def test_axisymmetric_nurbs_open_impeller_uses_revolved_hub_tip_and_conformal_blade_sides():
    parameters = {
        "blade_count": 7,
        "inlet_radius_mm": 180.0,
        "exit_radius_mm": 620.0,
        "inlet_blade_height_mm": 150.0,
        "outlet_blade_height_mm": 72.0,
        "inlet_blade_angle_deg": 21.0,
        "outlet_blade_angle_deg": 42.0,
        "blade_thickness_mm": 18.0,
        "blade_curve_gain": 1.0,
        "hub_curve_height_mm": 82.0,
        "blade_wrap_deg": 118.0,
        "blade_lean_deg": 8.0,
    }
    facets = {
        "flow_topology": "radial",
        "shroud_topology": "open",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    geometry = build_impeller_geometry(parameters, facets)
    surfaces = {surface["id"]: surface for surface in geometry["surface_graph"]["surfaces"]}
    first_blade = geometry["sampled_blades"][0]

    assert geometry["kernel"]["kind"] == "axisymmetric_throughflow_nurbs_kernel"
    assert geometry["kernel"]["uv_sampling"] == {
        "surface_u_count": 41,
        "surface_v_count": 33,
        "blade_u_count": 41,
        "blade_v_count": 17,
    }
    assert surfaces["hub_revolve_surface"]["kind"] == "nurbs_revolve_surface"
    assert surfaces["tip_reference_surface"]["kind"] == "nurbs_revolve_surface"
    assert surfaces["hub_revolve_surface"]["profile"]["kind"] == "nurbs_curve"
    assert surfaces["tip_reference_surface"]["profile"]["kind"] == "nurbs_curve"
    assert surfaces["blade_0_pressure_surface"]["kind"] == "nurbs_surface"
    assert surfaces["blade_0_suction_surface"]["kind"] == "nurbs_surface"
    hub_control_points = surfaces["hub_revolve_surface"]["profile"]["control_points"]
    bottom_hub_point = min(hub_control_points, key=lambda point: point[1])
    top_hub_point = max(hub_control_points, key=lambda point: point[1])
    assert bottom_hub_point[0] > top_hub_point[0]
    assert surfaces["inner_hub_bottom_face"]["kind"] == "annular_plane_surface"
    assert surfaces["mounting_bore_cylinder"]["kind"] == "cylindrical_surface"
    assert surfaces["outer_hub_shell_surface"]["kind"] == "nurbs_revolve_surface"
    assert len(surfaces["hub_revolve_surface"]["uv_grid"]) == 41
    assert len(surfaces["hub_revolve_surface"]["uv_grid"][0]) == 33
    assert len(first_blade["pressure_surface"]) == 41
    assert len(first_blade["pressure_surface"][0]) == 17
    assert first_blade["pressure_surface"][0][0] == first_blade["pressure_hub_boundary"][0]
    assert first_blade["suction_surface"][0][0] == first_blade["suction_hub_boundary"][0]
    assert first_blade["pressure_surface"][0][-1] == first_blade["pressure_tip_boundary"][0]
    assert first_blade["suction_surface"][0][-1] == first_blade["suction_tip_boundary"][0]
    topology_checks = {check["name"]: check for check in geometry["validity"]["topology_checks"]}
    assert topology_checks["pressure_surface_hub_conformance"]["status"] == "PASS"
    assert topology_checks["suction_surface_hub_conformance"]["status"] == "PASS"
    assert topology_checks["pressure_surface_tip_conformance"]["status"] == "PASS"
    assert topology_checks["suction_surface_tip_conformance"]["status"] == "PASS"
    assert topology_checks["blade_edge_surfaces_present"]["status"] == "PASS"
    assert topology_checks["blade_surface_closure_candidate"]["status"] == "PASS"


def test_axisymmetric_nurbs_hub_orientation_and_construction_sequence_are_explicit():
    parameters = {
        "blade_count": 7,
        "inlet_radius_mm": 180.0,
        "exit_radius_mm": 620.0,
        "inlet_blade_height_mm": 150.0,
        "outlet_blade_height_mm": 72.0,
        "inlet_blade_angle_deg": 21.0,
        "outlet_blade_angle_deg": 42.0,
        "blade_thickness_mm": 18.0,
        "hub_curve_height_mm": 82.0,
        "mounting_bore_radius_mm": 40.0,
        "blade_wrap_deg": 118.0,
        "blade_lean_deg": 8.0,
    }
    facets = {
        "flow_topology": "radial",
        "shroud_topology": "open",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    geometry = build_impeller_geometry(parameters, facets)
    hub_surface = {
        surface["id"]: surface
        for surface in geometry["surface_graph"]["surfaces"]
    }["hub_revolve_surface"]
    sampled_profile = hub_surface["profile_samples_rz"]

    assert geometry["kernel"]["hub_profile_orientation"] == {
        "u0": "top_eye_small_radius",
        "u1": "bottom_backplate_large_radius",
    }
    assert sampled_profile[0]["z_mm"] > sampled_profile[-1]["z_mm"]
    assert sampled_profile[0]["r_mm"] < sampled_profile[-1]["r_mm"]
    assert all(
        current["r_mm"] <= next_point["r_mm"]
        for current, next_point in zip(sampled_profile, sampled_profile[1:])
    )
    assert all(
        current["z_mm"] >= next_point["z_mm"]
        for current, next_point in zip(sampled_profile, sampled_profile[1:])
    )
    assert len(geometry["kernel"]["construction_sequence"]) >= 7
    assert "hub" in geometry["kernel"]["construction_sequence"][1].lower()
    assert "blade edge" in " ".join(geometry["kernel"]["construction_sequence"]).lower()


def test_axisymmetric_nurbs_blade_has_le_te_root_and_tip_closure_surfaces():
    parameters = {
        "blade_count": 7,
        "inlet_radius_mm": 180.0,
        "exit_radius_mm": 620.0,
        "inlet_blade_height_mm": 150.0,
        "outlet_blade_height_mm": 72.0,
        "inlet_blade_angle_deg": 21.0,
        "outlet_blade_angle_deg": 42.0,
        "blade_thickness_mm": 18.0,
        "blade_curve_gain": 1.0,
        "hub_curve_height_mm": 82.0,
        "blade_wrap_deg": 118.0,
        "blade_lean_deg": 8.0,
    }
    facets = {
        "flow_topology": "radial",
        "shroud_topology": "open",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    geometry = build_impeller_geometry(parameters, facets)
    surfaces = {surface["id"]: surface for surface in geometry["surface_graph"]["surfaces"]}
    edges = {edge["id"]: edge for edge in geometry["surface_graph"]["edges"]}

    for surface_id in [
        "blade_0_leading_edge_surface",
        "blade_0_trailing_edge_surface",
        "blade_0_root_closure_surface",
        "blade_0_tip_closure_surface",
    ]:
        assert surface_id in surfaces
        assert surfaces[surface_id]["kind"] == "edge_closure_surface"

    assert surfaces["blade_0_leading_edge_surface"]["uv_grid"][0][0] == surfaces["blade_0_pressure_surface"]["uv_grid"][0][0]
    assert surfaces["blade_0_leading_edge_surface"]["uv_grid"][0][-1] == surfaces["blade_0_suction_surface"]["uv_grid"][0][0]
    assert surfaces["blade_0_trailing_edge_surface"]["uv_grid"][-1][0] == surfaces["blade_0_pressure_surface"]["uv_grid"][-1][-1]
    assert surfaces["blade_0_trailing_edge_surface"]["uv_grid"][-1][-1] == surfaces["blade_0_suction_surface"]["uv_grid"][-1][-1]
    assert surfaces["blade_0_root_closure_surface"]["uv_grid"][0][0] == surfaces["blade_0_pressure_surface"]["uv_grid"][0][0]
    assert surfaces["blade_0_tip_closure_surface"]["uv_grid"][-1][-1] == surfaces["blade_0_suction_surface"]["uv_grid"][-1][-1]
    assert edges["blade_0_pressure_leading_edge"]["relation"] == "closed_blade_edge"
    assert edges["blade_0_suction_trailing_edge"]["relation"] == "closed_blade_edge"


def test_v06_surface_graph_emits_cad_surface_payloads():
    from part_rule_synthesis.impeller_runtime_compiler import compile_impeller_runtime_preset
    from part_rule_synthesis.service import _bind_parameters, _geometry_metadata

    surface_sets = {}
    for preset_id in ["radial_open_reference_v0_6", "radial_closed_reference_v0_6"]:
        runtime = compile_impeller_runtime_preset(preset_id)
        parameters = _bind_parameters(runtime, {})
        geometry = _geometry_metadata(
            "impeller",
            parameters,
            runtime["facets"],
            dsl_context=runtime,
        )
        surfaces = {surface["id"]: surface for surface in geometry["surface_graph"]["surfaces"]}
        missing_payloads = [
            surface_id
            for surface_id, surface in surfaces.items()
            if "cad_surface" not in surface
        ]

        assert missing_payloads == []
        surface_sets[preset_id] = surfaces

    surfaces = surface_sets["radial_open_reference_v0_6"]

    pressure = surfaces["blade_0_pressure_surface"]
    hub = surfaces["hub_revolve_surface"]
    bottom = surfaces["inner_hub_bottom_face"]

    assert pressure["cad_surface"]["surface_type"] == "bspline_surface"
    assert pressure["cad_surface"]["degree_u"] == 3
    assert pressure["cad_surface"]["degree_v"] == 3
    assert hub["cad_surface"]["surface_type"] in {"bspline_surface", "revolved_bspline_surface"}
    assert bottom["cad_surface"]["surface_type"] == "plane"


def test_v06_root_and_edge_fillets_are_explicit_design_surfaces():
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from part_rule_synthesis.service import RuleSynthesisService

    with TemporaryDirectory() as directory:
        service = RuleSynthesisService(Path(directory))
        engine = service.synthesize("impeller", "radial_open_reference_v0_6")
        run = service.instantiate(engine.engine_id, {"root_fillet_radius_mm": 10.0})

    surfaces = {surface["id"]: surface for surface in run.manifest["geometry"]["surface_graph"]["surfaces"]}
    root = surfaces["blade_0_root_fillet_surface"]
    leading = surfaces["blade_0_leading_edge_fillet_surface"]
    trailing = surfaces["blade_0_trailing_edge_fillet_surface"]
    validity_check_names = {
        check["name"]
        for check in run.manifest["geometry"]["validity"]["geometry_checks"]
    }
    manifest_validity_check_names = {
        check["name"]
        for check in run.manifest["geometry_validity"]["geometry_checks"]
    }

    assert root["role"] == "blade_root_fillet"
    assert root["radius_mm"] == 10.0
    assert root["cad_surface"]["surface_type"] == "bspline_surface"
    assert leading["role"] == "blade_leading_edge_fillet"
    assert trailing["role"] == "blade_trailing_edge_fillet"
    assert "fillet_radius_within_local_thickness_bounds" in validity_check_names
    assert "fillet_radius_within_local_thickness_bounds" in manifest_validity_check_names


def test_axisymmetric_nurbs_blade_edges_are_visible_construction_lines_from_closure_surfaces():
    parameters = {
        "blade_count": 7,
        "inlet_radius_mm": 180.0,
        "exit_radius_mm": 620.0,
        "inlet_blade_height_mm": 150.0,
        "outlet_blade_height_mm": 72.0,
        "inlet_blade_angle_deg": 21.0,
        "outlet_blade_angle_deg": 42.0,
        "blade_thickness_mm": 18.0,
        "hub_curve_height_mm": 82.0,
        "mounting_bore_radius_mm": 40.0,
        "blade_wrap_deg": 118.0,
        "blade_lean_deg": 8.0,
    }
    facets = {
        "flow_topology": "radial",
        "shroud_topology": "open",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    geometry = build_impeller_geometry(parameters, facets)
    surfaces = {surface["id"]: surface for surface in geometry["surface_graph"]["surfaces"]}
    edge_lines = geometry["construction_lines"]["blade_edges"]
    blade_0_edge_roles = {
        line["role"]
        for line in edge_lines
        if line["blade_index"] == 0
    }

    assert {
        "leading_edge_pressure",
        "leading_edge_suction",
        "trailing_edge_pressure",
        "trailing_edge_suction",
        "root_edge_pressure",
        "root_edge_suction",
        "tip_edge_pressure",
        "tip_edge_suction",
    }.issubset(blade_0_edge_roles)
    assert all(line["source"] == "axisymmetric_throughflow_nurbs.edge_closure_surface" for line in edge_lines)
    assert surfaces["blade_0_leading_edge_surface"]["display"]["edge_highlight"] is True
    leading_pressure = next(
        line for line in edge_lines
        if line["blade_index"] == 0 and line["role"] == "leading_edge_pressure"
    )
    assert leading_pressure["points"] == [
        row[0] for row in surfaces["blade_0_leading_edge_surface"]["uv_grid"]
    ]


def test_axisymmetric_nurbs_closed_impeller_uses_shroud_surface_for_tip_boundary():
    parameters = {
        "blade_count": 6,
        "inlet_radius_mm": 190.0,
        "exit_radius_mm": 600.0,
        "inlet_blade_height_mm": 130.0,
        "outlet_blade_height_mm": 68.0,
        "inlet_blade_angle_deg": 22.0,
        "outlet_blade_angle_deg": 38.0,
        "blade_thickness_mm": 16.0,
        "blade_curve_gain": 1.0,
        "hub_curve_height_mm": 74.0,
        "blade_wrap_deg": 95.0,
        "blade_lean_deg": -5.0,
    }
    facets = {
        "flow_topology": "radial",
        "shroud_topology": "closed",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }

    geometry = build_impeller_geometry(parameters, facets)
    surfaces = {surface["id"]: surface for surface in geometry["surface_graph"]["surfaces"]}
    first_blade = geometry["sampled_blades"][0]

    assert geometry["kernel"]["kind"] == "axisymmetric_throughflow_nurbs_kernel"
    assert "tip_reference_surface" not in surfaces
    assert surfaces["shroud_surface"]["kind"] == "nurbs_revolve_surface"
    assert first_blade["pressure_surface"][-1][-1] == first_blade["pressure_tip_boundary"][-1]
    assert first_blade["suction_surface"][-1][-1] == first_blade["suction_tip_boundary"][-1]
    assert any(
        edge["relation"] == "conformal_tip_boundary"
        and set(edge["surfaces"]) == {"shroud_surface", "blade_0_pressure_surface"}
        for edge in geometry["surface_graph"]["edges"]
    )
