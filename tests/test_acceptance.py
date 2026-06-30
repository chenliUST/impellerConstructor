import json
from pathlib import Path

from fastapi.testclient import TestClient

from part_rule_synthesis.api import create_app
from part_rule_synthesis.service import RuleSynthesisService


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


def test_acceptance_impeller_ontology_exposes_axisymmetric_radial_slice(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    ontology = client.get("/api/ontology").json()
    impeller = ontology["part_families"]["impeller"]

    assert impeller["ontology_slices"]["axisymmetric_throughflow_radial_bladed"]["constructor_family"] == (
        "AxisymmetricThroughflowRadialBladedImpeller"
    )
    assert impeller["ontology_slices"]["axisymmetric_throughflow_radial_bladed"]["flow_topology"] == ["radial"]
    assert "blade_tip_support_surface" in ontology["terms"]
    assert "leading_edge_boundary" in ontology["terms"]
    assert "trailing_edge_boundary" in ontology["terms"]
    assert "shape_control_policy" in ontology["terms"]
    assert "semantic_handle" in ontology["terms"]


def test_acceptance_legacy_impeller_preset_alias_compiles_to_new_constructor_family(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "axisymmetric_nurbs_open_throughflow_study"},
    )

    assert engine.status_code == 200
    payload = engine.json()
    rule = json.loads(Path(payload["dsl_path"]).read_text(encoding="utf-8"))
    assert rule["preset_id"] == "radial_open_reference"
    assert rule["legacy_preset_id"] == "axisymmetric_nurbs_open_throughflow_study"
    assert rule["ontology_slice"] == "impeller.axisymmetric_throughflow_radial_bladed"
    assert rule["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert rule["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open"
    assert rule["shape_control"]["optimization_stage"] == 1
    assert rule["shape_control"]["locked_topology"] is True


def test_acceptance_impeller_manifest_includes_ontology_constructor_validity_loss_and_shape_control(
    tmp_path: Path,
):
    client = TestClient(create_app(tmp_path))
    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_open_reference"},
    ).json()

    manifest = client.post(
        f"/api/rule-engines/{engine['engine_id']}/instantiate",
        json={"parameters": {}},
    ).json()["manifest"]

    assert manifest["ontology_slice"] == "impeller.axisymmetric_throughflow_radial_bladed"
    assert manifest["constructor_family"] == "AxisymmetricThroughflowRadialBladedImpeller"
    assert manifest["constructor_id"] == "axisymmetric_throughflow_radial_bladed.open"
    assert manifest["dsl_version"] == "0.2"
    assert manifest["shape_control"]["optimization_stage"] == 1
    assert manifest["shape_control"]["locked_topology"] is True
    assert manifest["shape_control"]["shape_optimization_space"]["editable_variables"]
    assert manifest["shape_control"]["provenance"]["source"] in {
        "default_rule",
        "explicit_dsl_control_net",
        "human_patch",
        "optimizer_patch",
    }
    assert "geometry_contracts" in manifest["validity"]
    assert "topology_contracts" in manifest["validity"]
    assert "engineering_warnings" in manifest["validity"]
    assert manifest["loss_records"] == []


def test_acceptance_impeller_instantiate_accepts_profile_curve_overrides_and_stage(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference", {})
    default_run = service.instantiate(engine.engine_id, {})
    hub = default_run.manifest["geometry_kernel"]["meridional_profiles"]["hub"]
    tip = default_run.manifest["geometry_kernel"]["meridional_profiles"]["tip_or_shroud"]
    edited_hub = {
        **hub,
        "control_points": [
            [point[0] + (4.0 if index == 1 else 0.0), point[1]]
            for index, point in enumerate(hub["control_points"])
        ],
    }

    run = service.instantiate(
        engine.engine_id,
        {},
        profile_overrides={"hub_profile": edited_hub, "tip_or_shroud_profile": tip},
        geometry_stage="hub_support",
    )

    assert run.run_id != default_run.run_id
    assert run.manifest["geometry_stage"] == "hub_support"
    assert run.manifest["profile_overrides"]["hub_profile"]["control_points"] == edited_hub["control_points"]
    assert run.manifest["curve_overrides"] == {}
    assert all(
        surface["role"] in {"hub", "outer_hub_shell", "inner_hub_bottom", "mounting_bore", "reference_only", "front_shroud_inner_surface"}
        for surface in run.manifest["geometry"]["surface_graph"]["surfaces"]
    )


def test_acceptance_impeller_instantiate_accepts_curve_overrides(tmp_path: Path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", "radial_open_reference", {})

    run = service.instantiate(
        engine.engine_id,
        {},
        curve_overrides={
            "blade_mean": {
                "theta_center_u_curve": {
                    "coordinate_system": "u_theta_deg",
                    "control_points": [[0.0, 0.0], [0.33, -20.0], [0.66, -70.0], [1.0, -118.0]],
                },
                "span_lean_u_curve": {
                    "coordinate_system": "u_lean_deg",
                    "control_points": [[0.0, 12.0], [0.5, 8.0], [1.0, -8.0]],
                },
            },
            "blade_edges": {
                "leading_edge_sweep_v_curve": {
                    "coordinate_system": "v_support_u_offset",
                    "control_points": [[0.0, -0.03], [0.5, 0.0], [1.0, 0.03]],
                },
                "trailing_edge_sweep_v_curve": {
                    "coordinate_system": "v_support_u_offset",
                    "control_points": [[0.0, 0.05], [0.5, 0.0], [1.0, -0.05]],
                },
            },
            "thickness": {
                "thickness_u_curve": {
                    "coordinate_system": "u_thickness_mm",
                    "control_points": [[0.0, 18.0], [0.5, 14.0], [1.0, 10.0]],
                }
            },
        },
        geometry_stage="blade_surfaces",
    )

    assert run.manifest["geometry_stage"] == "blade_surfaces"
    assert run.manifest["curve_overrides"]["blade_mean"]["theta_center_u_curve"]["coordinate_system"] == "u_theta_deg"
    assert any(surface["role"] == "blade_pressure" for surface in run.manifest["geometry"]["surface_graph"]["surfaces"])
    assert not any(surface["kind"] == "edge_closure_surface" for surface in run.manifest["geometry"]["surface_graph"]["surfaces"])


def test_acceptance_impeller_instantiate_rejects_invalid_geometry_stage(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_open_reference"},
    ).json()

    response = client.post(
        f"/api/rule-engines/{engine['engine_id']}/instantiate",
        json={"parameters": {}, "geometry_stage": "floating_blades"},
    )

    assert response.status_code == 400
    assert "invalid geometry stage" in response.json()["detail"]


def test_acceptance_open_and_closed_impellers_share_tip_support_surface_semantics(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    cases = [
        ("radial_open_reference", "reference_only", False),
        ("radial_closed_reference", "front_shroud_inner_surface", True),
    ]

    for preset_id, expected_role, expected_material in cases:
        engine = client.post(
            "/api/rule-engines/synthesize",
            json={"part_family_id": "impeller", "preset_id": preset_id},
        ).json()
        manifest = client.post(
            f"/api/rule-engines/{engine['engine_id']}/instantiate",
            json={"parameters": {}},
        ).json()["manifest"]
        tip_surfaces = [
            surface
            for surface in manifest["geometry"]["surface_graph"]["surfaces"]
            if surface.get("ontology_id") == "blade_tip_support_surface"
        ]

        assert len(tip_surfaces) == 1
        assert tip_surfaces[0]["role"] == expected_role
        assert tip_surfaces[0]["material"] is expected_material
        assert manifest["geometry"]["surface_graph"]["named_boundary_curves"]
        assert manifest["geometry"]["construction_lines"]["blade_boundaries"]


def test_acceptance_v03_open_impeller_hides_tip_support_and_records_finite_hub(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_open_reference_v0_3"},
    ).json()
    manifest = client.post(
        f"/api/rule-engines/{engine['engine_id']}/instantiate",
        json={"parameters": {}},
    ).json()["manifest"]

    surface_graph = manifest["geometry"]["surface_graph"]
    surfaces = {surface["id"]: surface for surface in surface_graph["surfaces"]}
    surface_uv_ids = {
        line["surface_id"]
        for line in manifest["geometry"]["construction_lines"]["surface_uv"]
    }
    geometry_checks = {check["name"]: check for check in manifest["geometry_validity"]["geometry_checks"]}
    topology_checks = {check["name"]: check for check in manifest["geometry_validity"]["topology_checks"]}

    assert manifest["dsl_version"] == "0.3"
    assert "tip_reference_surface" not in surfaces
    assert "tip_reference_surface" not in surface_uv_ids
    assert "hub_top_cap_face" in surfaces
    assert "hub_chamfer_top_cap_surface" in surfaces
    assert surfaces["mounting_bore_cylinder"]["role"] == "mounting_bore"
    assert manifest["geometry_kernel"]["material_domains"]["hub"]["kind"] == "capped_revolved_solid_with_bore"
    assert manifest["geometry_kernel"]["material_domains"]["hub"]["wall_thickness_mm"] > 0.0
    assert geometry_checks["material_domain_positive_thickness"]["status"] == "PASS"
    assert topology_checks["open_tip_support_surface_hidden_from_display_graph"]["status"] == "PASS"
    assert topology_checks["hub_solid_has_caps_and_bore"]["status"] == "PASS"


def test_acceptance_v03_closed_impeller_displays_finite_hood_shell(tmp_path: Path):
    client = TestClient(create_app(tmp_path))

    engine = client.post(
        "/api/rule-engines/synthesize",
        json={"part_family_id": "impeller", "preset_id": "radial_closed_reference_v0_3"},
    ).json()
    manifest = client.post(
        f"/api/rule-engines/{engine['engine_id']}/instantiate",
        json={"parameters": {}},
    ).json()["manifest"]

    surfaces = {surface["id"]: surface for surface in manifest["geometry"]["surface_graph"]["surfaces"]}
    geometry_checks = {check["name"]: check for check in manifest["geometry_validity"]["geometry_checks"]}
    topology_checks = {check["name"]: check for check in manifest["geometry_validity"]["topology_checks"]}

    assert manifest["dsl_version"] == "0.3"
    assert surfaces["shroud_surface"]["role"] == "front_shroud_inner_surface"
    assert "hood_outer_surface" in surfaces
    assert "hood_outlet_cap_surface" in surfaces
    assert manifest["geometry_kernel"]["material_domains"]["front_hood"]["kind"] == "finite_thickness_revolved_shell"
    assert manifest["geometry_kernel"]["material_domains"]["front_hood"]["wall_thickness_mm"] > 0.0
    assert geometry_checks["material_domain_positive_thickness"]["status"] == "PASS"
    assert topology_checks["closed_hood_shell_surfaces_present"]["status"] == "PASS"


def test_impeller_v04_manifest_includes_cfd_full_360_patch_groups(tmp_path):
    service = RuleSynthesisService(tmp_path)
    engine = service.synthesize("impeller", preset_id="radial_open_reference_v0_4")
    parameters = {name: spec["default"] for name, spec in service.engines[engine.engine_id]["parameters"].items()}

    run = service.instantiate(engine.engine_id, parameters)
    cfd = run.manifest["simulation_manifests"]["cfd_full_360"]

    assert cfd["domain_kind"] == "full_360_wetted_surface"
    assert "blade_pressure_wall" in cfd["patch_groups"]
    assert "blade_suction_wall" in cfd["patch_groups"]
    assert cfd["feature_suppression"]["suppressed_features"]
    assert cfd["validity"]["status"] in {"PASS", "FAIL"}


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
