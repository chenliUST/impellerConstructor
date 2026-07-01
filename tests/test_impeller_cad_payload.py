from part_rule_synthesis.impeller_cad_payload import (
    boundary_edge_payload,
    bspline_surface_payload_from_control_net,
    knot_values_and_multiplicities,
)


def test_knot_values_and_multiplicities_compacts_clamped_knots():
    values, multiplicities = knot_values_and_multiplicities([0, 0, 0, 0, 0.5, 1, 1, 1, 1])

    assert values == [0.0, 0.5, 1.0]
    assert multiplicities == [4, 1, 4]


def test_bspline_surface_payload_from_control_net():
    surface = {
        "id": "blade_0_pressure_surface",
        "role": "blade_pressure",
        "feature_id": "blade_00",
        "degree_u": 3,
        "degree_v": 3,
        "control_net": [
            [[0, 0, 0], [0, 1, 0], [0, 2, 0], [0, 3, 0]],
            [[1, 0, 0], [1, 1, 0.2], [1, 2, 0.2], [1, 3, 0]],
            [[2, 0, 0], [2, 1, 0.2], [2, 2, 0.2], [2, 3, 0]],
            [[3, 0, 0], [3, 1, 0], [3, 2, 0], [3, 3, 0]],
        ],
    }

    payload = bspline_surface_payload_from_control_net(surface)

    assert payload["surface_type"] == "bspline_surface"
    assert payload["degree_u"] == 3
    assert payload["degree_v"] == 3
    assert payload["control_points"][0][0] == [0.0, 0.0, 0.0]
    assert payload["weights"][0][0] == 1.0
    assert payload["knots_u"] == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    assert payload["knots_v"] == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]


def test_boundary_edge_payload_uses_bspline_curve_shape():
    edge = boundary_edge_payload(
        "blade_0_pressure_leading_edge",
        [[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]],
        surface_uv={"blade_0_pressure_surface": [[0, 0], [0.33, 0], [0.66, 0], [1, 0]]},
    )

    assert edge["id"] == "blade_0_pressure_leading_edge"
    assert edge["cad_edge"]["curve_type"] == "bspline_curve"
    assert edge["cad_edge"]["degree"] == 3
    assert edge["cad_edge"]["surface_uv"]["blade_0_pressure_surface"]["control_points"][-1] == [
        1.0,
        0.0,
    ]
