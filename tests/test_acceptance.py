from pathlib import Path

from fastapi.testclient import TestClient

from part_rule_synthesis.api import create_app


def test_acceptance_ontology_and_primitives_are_queryable(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    ontology = client.get("/api/ontology").json()
    primitives = client.get("/api/primitives").json()

    assert {"hub", "blade_root", "inner_ring", "outer_ring", "vane"}.issubset(ontology["terms"])
    assert {"embedded_contact", "bridges", "bounds_flow_path"}.issubset(ontology["relations"])
    assert {"bspline_section_curve", "lofted_blade_surface", "circular_pattern"}.issubset(
        primitives["items"]
    )


def test_acceptance_impeller_ontology_exposes_facets_and_presets(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    ontology = client.get("/api/ontology").json()
    presets = client.get("/api/impeller-presets")

    assert presets.status_code == 200
    assert ontology["part_families"]["impeller"]["facet_axes"]["flow_topology"] == [
        "axial",
        "mixed",
        "radial",
    ]
    assert ontology["part_families"]["impeller"]["facet_axes"]["shroud_topology"] == [
        "open",
        "semi_open",
        "closed",
    ]
    assert ontology["part_families"]["impeller"]["facet_axes"]["passage_topology"] == [
        "throughflow_bladed_channel",
        "single_channel",
        "multi_channel",
        "recessed_vortex",
        "cutter",
    ]
    preset_payload = presets.json()["presets"]
    assert {preset["preset_id"] for preset in preset_payload}.issuperset(
        {
            "radial_open_backward_single_reference",
            "mixed_semi_open_radial_double_study",
            "axial_closed_forward_single_study",
            "radial_open_recessed_vortex_study",
            "twisted_open_impeller_study",
            "twisted_closed_impeller_study",
            "axisymmetric_nurbs_open_throughflow_study",
            "axisymmetric_nurbs_closed_throughflow_study",
        }
    )
    assert all(preset["part_family_id"] == "impeller" for preset in preset_payload)


def test_acceptance_impeller_rule_engine_records_facets_rules_and_construction_lines(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine = client.post(
        "/api/rule-engines/synthesize",
        json={
            "part_family_id": "impeller",
            "preset_id": "radial_open_backward_single_reference",
            "facets": {"shroud_topology": "closed"},
        },
    )
    assert engine.status_code == 200
    engine_payload = engine.json()

    manifest = client.post(
        f"/api/rule-engines/{engine_payload['engine_id']}/instantiate",
        json={"parameters": {"blade_count": 8, "blade_curve_gain": 1.6, "hub_curve_height_mm": 160.0}},
    ).json()["manifest"]

    assert engine_payload["part_family_id"] == "impeller"
    assert manifest["part_family"] == "impeller"
    assert manifest["preset_id"] == "radial_open_backward_single_reference"
    assert manifest["facets"] == {
        "flow_topology": "radial",
        "shroud_topology": "closed",
        "suction_topology": "single_suction",
        "blade_exit_geometry": "backward_curved",
        "working_domain": "pump",
        "passage_topology": "throughflow_bladed_channel",
    }
    assert "flow_topology.radial.requires_outlet_radius_gt_inlet_radius" in manifest["selected_rules"]
    assert "shroud_topology.closed.generates_front_and_back_shroud_parameter_lines" in manifest["selected_rules"]
    assert manifest["rule_implications"]["flow_topology"] == "radial outlet radius must exceed inlet radius"
    assert manifest["geometry_kernel"]["kind"] == "meridional_beta_thickness_kernel"
    assert manifest["geometry_kernel"]["uv_sampling"] == {"u_count": 9, "v_count": 5}
    assert manifest["geometry"]["construction_lines"]["hub"]
    assert manifest["geometry"]["construction_lines"]["blade_u"]
    assert manifest["geometry"]["construction_lines"]["blade_v"]
    assert manifest["geometry"]["construction_lines"]["surface_uv"]
    assert manifest["geometry"]["surface_graph"]["surfaces"]
    assert manifest["geometry"]["surface_graph"]["edges"]
    surface_ids = {surface["id"] for surface in manifest["geometry"]["surface_graph"]["surfaces"]}
    assert "hub_revolve_surface" in surface_ids
    assert "blade_0_root_fillet_surface" in surface_ids
    assert "blade_0_leading_edge_fillet_surface" in surface_ids
    assert "blade_0_trailing_edge_fillet_surface" in surface_ids
    assert manifest["geometry_validity"]["status"] == "PASS"
    assert "geometry_validity_passed" in manifest["validation"]["checks"]
    assert "topology_validity_passed" in manifest["validation"]["checks"]
    assert manifest["geometry"]["construction_lines"]["shroud"]
    assert "closed_shroud_proxy" in manifest["geometry"]["cad_features"]
    assert manifest["unsupported_or_inferred_regions"]
    assert client.get(f"/api/model-runs/{manifest['run_id']}/exports/stl").status_code == 200


def test_acceptance_impeller_construction_lines_are_derived_from_loft_geometry(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine = client.post(
        "/api/rule-engines/synthesize",
        json={
            "part_family_id": "impeller",
            "preset_id": "radial_open_backward_single_reference",
            "facets": {
                "flow_topology": "mixed",
                "shroud_topology": "closed",
                "suction_topology": "double_suction",
                "blade_exit_geometry": "forward_curved",
                "working_domain": "turbine_or_runner",
                "passage_topology": "throughflow_bladed_channel",
            },
        },
    ).json()
    manifest = client.post(
        f"/api/rule-engines/{engine['engine_id']}/instantiate",
        json={"parameters": {"hub_curve_height_mm": 160.0}},
    ).json()["manifest"]

    blade_u_lines = manifest["geometry"]["construction_lines"]["blade_u"]
    blade_v_lines = manifest["geometry"]["construction_lines"]["blade_v"]
    shroud_lines = manifest["geometry"]["construction_lines"]["shroud"]
    first_blade = manifest["geometry"]["sampled_blades"][0]["mean_surface"]

    assert "mixed_flow_axial_offset_proxy" in manifest["geometry"]["cad_features"]
    assert "closed_shroud_proxy" in manifest["geometry"]["cad_features"]
    assert "double_suction_mirror_proxy" in manifest["geometry"]["cad_features"]
    assert all(line["source"] == "impeller_kernel.blade_surface" for line in blade_u_lines)
    assert all(line["source"] == "impeller_kernel.blade_surface" for line in blade_v_lines)
    assert blade_u_lines[0]["points"] == first_blade[0]
    assert blade_v_lines[0]["points"] == [row[0] for row in first_blade]
    all_blade_points = [point for line in blade_u_lines + blade_v_lines for point in line["points"]]
    assert min(point[2] for point in all_blade_points) < 0.0
    assert max(point[2] for point in all_blade_points) > 30.0
    assert all(line["source"] == "shroud_proxy" for line in shroud_lines)
    assert any(line["name"].startswith("front shroud") for line in shroud_lines)
    assert any("mirrored" in line["name"] for line in shroud_lines)


def test_acceptance_impeller_recessed_vortex_is_passage_topology_not_flow_topology(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine = client.post(
        "/api/rule-engines/synthesize",
        json={
            "part_family_id": "impeller",
            "preset_id": "radial_open_recessed_vortex_study",
        },
    )
    assert engine.status_code == 200
    engine_payload = engine.json()

    manifest = client.post(
        f"/api/rule-engines/{engine_payload['engine_id']}/instantiate",
        json={"parameters": {}},
    ).json()["manifest"]

    assert manifest["facets"]["flow_topology"] == "radial"
    assert manifest["facets"]["shroud_topology"] == "open"
    assert manifest["facets"]["passage_topology"] == "recessed_vortex"
    assert "passage_topology.recessed_vortex.generates_recessed_free_flow_geometry" in manifest["selected_rules"]
    assert "recessed_vortex_impeller_proxy" in manifest["geometry"]["cad_features"]
    assert "throughflow_channel_proxy" not in manifest["geometry"]["cad_features"]
    assert manifest["geometry_kernel"]["passage_model"] == {
        "type": "recessed_vortex",
        "throughflow_bladed_channel": False,
        "free_passage_cavity": True,
    }
    assert manifest["geometry"]["construction_lines"]["passage"]
    assert manifest["geometry"]["construction_lines"]["blade_u"]
    assert client.get(f"/api/model-runs/{manifest['run_id']}/exports/step").status_code == 200
    assert client.get(f"/api/model-runs/{manifest['run_id']}/exports/stl").status_code == 200


def test_acceptance_impeller_rejects_invalid_facet_values(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    response = client.post(
        "/api/rule-engines/synthesize",
        json={
            "part_family_id": "impeller",
            "preset_id": "radial_open_backward_single_reference",
            "facets": {"flow_topology": "diagonal"},
        },
    )

    assert response.status_code == 400
    assert "invalid facet flow_topology" in response.json()["detail"]


def test_acceptance_twisted_impeller_presets_report_boundary_conformance(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    for preset_id, shroud_topology in [
        ("twisted_open_impeller_study", "open"),
        ("twisted_closed_impeller_study", "closed"),
    ]:
        engine = client.post(
            "/api/rule-engines/synthesize",
            json={"part_family_id": "impeller", "preset_id": preset_id},
        )
        assert engine.status_code == 200
        manifest = client.post(
            f"/api/rule-engines/{engine.json()['engine_id']}/instantiate",
            json={"parameters": {}},
        ).json()["manifest"]

        assert manifest["preset_id"] == preset_id
        assert manifest["facets"]["shroud_topology"] == shroud_topology
        assert manifest["geometry_kernel"]["surface_fields"]["hub"]["twist_deg"] > 0.0
        assert manifest["geometry_kernel"]["surface_fields"]["tip"]["warp_mm"] > 0.0
        topology_checks = {check["name"]: check for check in manifest["geometry_validity"]["topology_checks"]}
        assert topology_checks["blade_hub_boundary_conformance"]["status"] == "PASS"
        assert topology_checks["blade_tip_boundary_conformance"]["status"] == "PASS"
        assert topology_checks["blade_hub_boundary_conformance"]["max_distance_mm"] == 0.0
        assert topology_checks["blade_tip_boundary_conformance"]["max_distance_mm"] == 0.0
        first_blade = manifest["geometry"]["sampled_blades"][0]
        assert first_blade["mean_surface"][0][0] == first_blade["hub_boundary"][0]
        assert first_blade["mean_surface"][0][-1] == first_blade["tip_boundary"][0]


def test_acceptance_axisymmetric_nurbs_open_and_closed_presets_use_high_density_surface_graph(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    for preset_id, expected_tip_surface_id in [
        ("axisymmetric_nurbs_open_throughflow_study", "tip_reference_surface"),
        ("axisymmetric_nurbs_closed_throughflow_study", "shroud_surface"),
    ]:
        engine = client.post(
            "/api/rule-engines/synthesize",
            json={"part_family_id": "impeller", "preset_id": preset_id},
        )
        assert engine.status_code == 200
        manifest = client.post(
            f"/api/rule-engines/{engine.json()['engine_id']}/instantiate",
            json={"parameters": {}},
        ).json()["manifest"]
        surfaces = {surface["id"]: surface for surface in manifest["geometry"]["surface_graph"]["surfaces"]}
        first_blade = manifest["geometry"]["sampled_blades"][0]

        assert manifest["geometry_kernel"]["kind"] == "axisymmetric_throughflow_nurbs_kernel"
        assert manifest["geometry_kernel"]["hub_profile_orientation"]["u0"] == "top_eye_small_radius"
        assert "blade edge" in " ".join(manifest["geometry_kernel"]["construction_sequence"]).lower()
        assert manifest["geometry_kernel"]["uv_sampling"]["blade_u_count"] == 41
        assert manifest["geometry_kernel"]["uv_sampling"]["blade_v_count"] == 17
        assert surfaces["hub_revolve_surface"]["kind"] == "nurbs_revolve_surface"
        assert surfaces["hub_revolve_surface"]["profile_samples_rz"][0]["r_mm"] < surfaces["hub_revolve_surface"]["profile_samples_rz"][-1]["r_mm"]
        assert surfaces[expected_tip_surface_id]["kind"] == "nurbs_revolve_surface"
        assert surfaces["blade_0_pressure_surface"]["kind"] == "nurbs_surface"
        assert surfaces["blade_0_suction_surface"]["kind"] == "nurbs_surface"
        assert manifest["geometry"]["construction_lines"]["blade_edges"]
        assert first_blade["pressure_surface"][0][0] == first_blade["pressure_hub_boundary"][0]
        assert first_blade["pressure_surface"][0][-1] == first_blade["pressure_tip_boundary"][0]
        topology_checks = {check["name"]: check for check in manifest["geometry_validity"]["topology_checks"]}
        assert topology_checks["pressure_surface_hub_conformance"]["status"] == "PASS"
        assert topology_checks["pressure_surface_tip_conformance"]["status"] == "PASS"


def test_acceptance_turbine_rotor_generates_deterministic_analysis_ready_exports(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine_id = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "turbine_rotor"},
    ).json()["engine_id"]

    payload = {"parameters": {"blade_count": 18, "hub_radius_mm": 18.0}}
    first = client.post(f"/api/rule-engines/{engine_id}/instantiate", json=payload).json()["manifest"]
    second = client.post(f"/api/rule-engines/{engine_id}/instantiate", json=payload).json()["manifest"]

    assert first["operation_graph_hash"] == second["operation_graph_hash"]
    assert first["validation"]["status"] == "PASS"
    assert "embedded_contact_blade_root_hub" in first["validation"]["checks"]
    assert first["geometry"]["airfoil"]["authority"] == "inferred"
    assert first["geometry"]["airfoil"]["curve"]["kind"] == "bspline"
    assert first["geometry"]["named_regions"] == ["hub.outer_surface", "blade_root", "blade_airfoil"]
    assert client.get(f"/api/model-runs/{first['run_id']}/exports/step").status_code == 200
    assert client.get(f"/api/model-runs/{first['run_id']}/exports/stl").status_code == 200


def test_acceptance_ngv_generates_bridge_validation_for_inner_and_outer_rings(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine_id = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "ngv_ring"},
    ).json()["engine_id"]
    manifest = client.post(
        f"/api/rule-engines/{engine_id}/instantiate",
        json={"parameters": {"vane_count": 21, "inner_radius_mm": 34.0}},
    ).json()["manifest"]

    assert manifest["part_family"] == "ngv_ring"
    assert "vane_bridges_inner_outer_rings" in manifest["validation"]["checks"]
    assert manifest["geometry"]["named_regions"] == ["inner_ring", "outer_ring", "vane", "flow_path"]


def test_acceptance_centrifugal_impeller_generates_backswept_blade_rule_engine(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine_id = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "centrifugal_impeller"},
    ).json()["engine_id"]
    payload = {
        "parameters": {
            "blade_count": 7,
            "inlet_radius_mm": 420.2,
            "exit_radius_mm": 1400.65,
            "backsweep_deg": 35.0,
        }
    }
    first = client.post(f"/api/rule-engines/{engine_id}/instantiate", json=payload).json()["manifest"]
    second = client.post(f"/api/rule-engines/{engine_id}/instantiate", json=payload).json()["manifest"]

    assert first["part_family"] == "centrifugal_impeller"
    assert first["operation_graph_hash"] == second["operation_graph_hash"]
    assert {"inducer", "hub.outer_surface", "blade_root", "blade_airfoil", "radial_exit"}.issubset(
        first["geometry"]["named_regions"]
    )
    assert first["geometry"]["airfoil"]["authority"] == "inferred"
    assert first["geometry"]["airfoil"]["curve"]["kind"] == "bspline"
    assert "backswept_blade_curve_present" in first["validation"]["checks"]
    assert "radial_exit_greater_than_inlet" in first["validation"]["checks"]
    assert any(step["feature"] == "inducer" for step in first["operation_graph"])
    assert any(step.get("backsweep_deg") == 35.0 for step in first["operation_graph"])
    assert client.get(f"/api/model-runs/{first['run_id']}/exports/step").status_code == 200
    assert client.get(f"/api/model-runs/{first['run_id']}/exports/stl").status_code == 200


def test_acceptance_centrifugal_impeller_uses_upcommons_reference_defaults_and_visible_blades(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "centrifugal_impeller"},
    ).json()
    manifest = client.post(
        f"/api/rule-engines/{engine['engine_id']}/instantiate",
        json={"parameters": {}},
    ).json()["manifest"]

    assert manifest["parameters"] == {
        "blade_count": 7,
        "inlet_radius_mm": 420.2,
        "exit_radius_mm": 1400.65,
        "inlet_blade_height_mm": 394.0,
        "outlet_blade_height_mm": 251.0,
        "inlet_blade_angle_deg": 17.47,
        "outlet_blade_angle_deg": 21.19,
        "blade_thickness_mm": 56.0,
    }
    assert "upcommons_centrifugal_pump_impeller" in manifest["source_refs"]
    assert manifest["primitive_version"] == "0.5.0"
    assert manifest["geometry"]["blade_surface_count"] == 7
    assert "hub_solid" in manifest["geometry"]["cad_features"]
    assert "backswept_blade_proxy" not in manifest["geometry"]["cad_features"]
    assert "lofted_blade_surface" in manifest["geometry"]["cad_features"]
    assert manifest["geometry"]["blade_surface"]["driven_by"] == [
        "inlet_blade_angle_deg",
        "outlet_blade_angle_deg",
        "blade_thickness_mm",
        "inlet_blade_height_mm",
        "outlet_blade_height_mm",
        "bspline_control_points",
    ]
    assert manifest["geometry"]["blade_surface"]["profile_curve_kind"] == "cadquery_spline"
    assert manifest["geometry_kernel"]["kind"] == "meridional_beta_thickness_kernel"
    assert manifest["geometry"]["blade_surface"]["height_model"] == "meridional_beta_thickness_kernel"
    assert manifest["geometry"]["blade_surface"]["loft_section_count"] == 5
    assert manifest["geometry"]["blade_surface"]["sections"][0]["radius_mm"] == 420.2
    assert manifest["geometry"]["blade_surface"]["sections"][-1]["radius_mm"] == 1400.65


def test_acceptance_centrifugal_impeller_high_curvature_variant_drives_hub_and_blade_surfaces(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "centrifugal_impeller"},
    ).json()
    manifest = client.post(
        f"/api/rule-engines/{engine['engine_id']}/instantiate",
        json={"parameters": {"blade_curve_gain": 2.4, "hub_curve_height_mm": 260.0}},
    ).json()["manifest"]

    assert manifest["primitive_version"] == "0.5.0"
    assert manifest["parameters"]["blade_curve_gain"] == 2.4
    assert manifest["parameters"]["hub_curve_height_mm"] == 260.0
    assert "curved_hub_surface" in manifest["geometry"]["cad_features"]
    assert manifest["geometry"]["hub_surface"] == {
        "primitive": "multi_section_lofted_hub_surface",
        "height_mm": 260.0,
        "section_count": 5,
    }
    assert manifest["geometry"]["blade_surface"]["curve_gain"] == 2.4
    assert max(section["angle_deg"] for section in manifest["geometry"]["blade_surface"]["sections"]) > 28.0


def test_acceptance_vague_human_feedback_becomes_rule_patch_proposal(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine_id = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "turbine_rotor"},
    ).json()["engine_id"]
    run_id = client.post(
        f"/api/rule-engines/{engine_id}/instantiate",
        json={"parameters": {"blade_count": 18, "hub_radius_mm": 18.0}},
    ).json()["run_id"]

    issue = client.post(
        f"/api/model-runs/{run_id}/feedback",
        json={
            "source": "human",
            "raw_feedback": "叶片没有正确长在轮毂上",
            "affected_feature": "blade_root",
        },
    ).json()
    patch = client.post(f"/api/feedback/{issue['issue_id']}/propose-patch").json()

    assert issue["classification"] == "rule_patch"
    assert issue["expected_relation"] == "embedded_contact(blade_root, hub.outer_surface)"
    assert patch["patch_type"] == "rule_patch"
    assert "embedded_contact" in patch["dsl_diff"]


def test_acceptance_missing_cad_capability_becomes_primitive_gap_not_auto_patch(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine_id = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "turbine_rotor"},
    ).json()["engine_id"]
    run_id = client.post(
        f"/api/rule-engines/{engine_id}/instantiate",
        json={"parameters": {"blade_count": 18, "hub_radius_mm": 18.0}},
    ).json()["run_id"]

    issue = client.post(
        f"/api/model-runs/{run_id}/feedback",
        json={"source": "human", "raw_feedback": "需要燕尾榫叶根，但是当前primitive无法表达"},
    ).json()
    patch = client.post(f"/api/feedback/{issue['issue_id']}/propose-patch").json()

    assert issue["classification"] == "primitive_gap"
    assert patch["patch_type"] == "primitive_gap"
    assert patch["approval_required"] is True


def test_acceptance_api_allows_vite_frontend_cors_preflight(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    for origin in ["http://localhost:5173", "http://127.0.0.1:5180", "http://127.0.0.1:5199"]:
        response = client.options(
            "/api/rule-engines/synthesize",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_acceptance_impeller_visual_frontend_can_generate_larger_blade_count(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    engine_id = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "centrifugal_impeller"},
    ).json()["engine_id"]

    manifest = client.post(
        f"/api/rule-engines/{engine_id}/instantiate",
        json={"parameters": {"blade_count": 10, "blade_curve_gain": 1.8, "hub_curve_height_mm": 180.0}},
    ).json()["manifest"]

    assert manifest["parameters"]["blade_count"] == 10
    assert manifest["geometry"]["blade_surface_count"] == 10
    assert "curved_hub_surface" in manifest["geometry"]["cad_features"]
