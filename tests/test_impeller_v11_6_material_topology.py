from __future__ import annotations

# ruff: noqa: E402

import copy
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = PROJECT_ROOT / "tests"
for path in (SRC_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from part_rule_synthesis.impeller_v11_6_pattern_reconstruction import (
    PatternReconstructionError,
    validate_mapped_pattern_reconstruction,
)
from part_rule_synthesis.impeller_v11_6_axis_first_pipeline import (
    task8_reconstruction_evidence_hash,
)
from test_impeller_v11_6_pattern_reconstruction import (
    _attachment,
    _different_sha256,
    _open_case,
    _periodic_evidence,
    _periodic_source_ids,
    _provenance,
    _runtime_graph,
    _task8_mapping,
    _task8_authority,
    _seal_periodic_evidence,
    _seal_support_evidence,
    _seal_support_record,
    _trusted_authority,
    _trusted_source_manifest,
    _validate_case,
)


def _closed_support(periodic: dict) -> dict:
    instance_ids = [
        instance["instance_id"]
        for population in periodic["populations"]
        for instance in population["instances"]
    ]
    hub_attachment = _attachment(instance_ids, "hub-attachment")
    shroud_attachment = _attachment(instance_ids, "shroud-attachment")
    hub_ids = ["hub-source-face"]
    inner_ids = ["shroud-inner-face"]
    outer_ids = ["shroud-outer-face"]
    all_source_ids = [
        *hub_ids,
        *inner_ids,
        *outer_ids,
        *hub_attachment["provenance"]["source_entity_ids"],
        *shroud_attachment["provenance"]["source_entity_ids"],
        *_periodic_source_ids(periodic),
    ]
    return {
        "status": "PASS",
        "authority": "authenticated_topology_support_v1_1_6",
        "mode": "closed",
        "provenance": _provenance(all_source_ids),
        "hub_support": {
            "status": "PASS",
            "semantic_role": "hub_support",
            "material": True,
            "source_face_ids": hub_ids,
            "blade_attachment": hub_attachment,
            "provenance": _provenance(hub_ids),
        },
        "open_tip_reference": None,
        "material_shroud": {
            "status": "PASS",
            "semantic_role": "closed_shroud",
            "material": True,
            "source_face_ids": [*inner_ids, *outer_ids],
            "inner_flowpath_face_ids": inner_ids,
            "outer_material_face_ids": outer_ids,
            "finite_thickness": {
                "samples_mm": [2.0, 2.1],
                "minimum_mm": 2.0,
                "source_face_pairs": [
                    ["shroud-inner-face", "shroud-outer-face"],
                    ["shroud-inner-face", "shroud-outer-face"],
                ],
                "finite_positive": True,
                "sampling_authority": "authenticated_paired_material_faces",
            },
            "blade_attachment": shroud_attachment,
            "provenance": _provenance([*inner_ids, *outer_ids]),
        },
    }


def _closed_case(graph: dict) -> tuple[dict, dict, dict]:
    periodic = _periodic_evidence(graph)
    support = _closed_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    authority = _trusted_authority(periodic, support, source_manifest)
    _seal_periodic_evidence(periodic, source_manifest)
    _seal_support_evidence(support, source_manifest)
    return periodic, support, authority


def test_closed_graph_requires_and_records_finite_shroud_plus_both_attachments():
    graph = copy.deepcopy(_runtime_graph("radial_closed_reference_v1_1"))
    periodic, support, trusted_authority = _closed_case(graph)

    decorated, manifest = _validate_case(graph, periodic, support, trusted_authority)

    material = manifest["material"]
    assert material["mode"] == "closed"
    assert material["material_shroud"]["material"] is True
    assert material["material_shroud"]["finite_thickness"]["minimum_mm"] == 2.0
    assert len(material["hub_support"]["blade_attachment"]["instance_ids"]) == 12
    assert len(material["material_shroud"]["blade_attachment"]["instance_ids"]) == 12
    shroud_surfaces = [surface for surface in decorated["surfaces"] if surface["role"] == "shroud_support"]
    shroud_attachments = [
        surface for surface in decorated["surfaces"] if surface["role"] == "closed_shroud_attachment"
    ]
    assert shroud_surfaces and shroud_attachments
    assert all(surface["material"] is True for surface in shroud_surfaces + shroud_attachments)
    assert all("periodic_pattern_binding" in surface for surface in shroud_attachments)


def test_mapped_adapter_preserves_closed_finite_shroud_and_both_attachments():
    graph = copy.deepcopy(_runtime_graph("radial_closed_reference_v1_1"))
    periodic = _periodic_evidence(graph)
    support = _closed_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    authority = _trusted_authority(periodic, support, source_manifest)
    material_partition = copy.deepcopy(authority["material_support_manifest"])
    material_partition["material_shroud"]["finite_thickness"] = copy.deepcopy(
        support["material_shroud"]["finite_thickness"]
    )
    mapping = _task8_mapping(periodic, material_partition, source_manifest)

    decorated, manifest = validate_mapped_pattern_reconstruction(
        graph,
        mapping,
        source_manifest,
        task8_recovery_authority=_task8_authority(mapping, source_manifest),
    )

    material = manifest["material"]
    assert material["mode"] == "closed"
    assert material["material_shroud"]["finite_thickness"]["minimum_mm"] == 2.0
    assert len(material["hub_support"]["blade_attachment"]["instance_ids"]) == 12
    assert len(
        material["material_shroud"]["blade_attachment"]["instance_ids"]
    ) == 12
    assert decorated["v1_1_6_pattern_material"]["status"] == "PASS"


def test_mapped_adapter_rejects_material_partition_changed_after_task8_seal():
    graph = copy.deepcopy(_runtime_graph("radial_closed_reference_v1_1"))
    periodic = _periodic_evidence(graph)
    support = _closed_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    authority = _trusted_authority(periodic, support, source_manifest)
    material_partition = copy.deepcopy(authority["material_support_manifest"])
    material_partition["material_shroud"]["finite_thickness"] = copy.deepcopy(
        support["material_shroud"]["finite_thickness"]
    )
    mapping = _task8_mapping(periodic, material_partition, source_manifest)
    authority = _task8_authority(mapping, source_manifest)
    mapping["support_recovery"]["pattern_material_partition"]["material_shroud"][
        "finite_thickness"
    ]["minimum_mm"] = 999.0
    mapping["task8_reconstruction_evidence_hash_sha256"] = (
        task8_reconstruction_evidence_hash(
            mapping["support_recovery"],
            mapping["periodic_provenance"],
            source_manifest["sha256"],
        )
    )

    with pytest.raises(PatternReconstructionError) as raised:
        validate_mapped_pattern_reconstruction(
            graph,
            mapping,
            source_manifest,
            task8_recovery_authority=authority,
        )

    assert raised.value.reason == "v116_task8_evidence_untrusted"


def test_mapped_adapter_rejects_malformed_resealed_attachment_with_stable_error():
    graph = copy.deepcopy(_runtime_graph("radial_closed_reference_v1_1"))
    periodic = _periodic_evidence(graph)
    support = _closed_support(periodic)
    source_manifest = _trusted_source_manifest(periodic, support)
    authority_manifest = _trusted_authority(periodic, support, source_manifest)
    material_partition = copy.deepcopy(
        authority_manifest["material_support_manifest"]
    )
    material_partition["material_shroud"]["finite_thickness"] = copy.deepcopy(
        support["material_shroud"]["finite_thickness"]
    )
    mapping = _task8_mapping(periodic, material_partition, source_manifest)
    task8_authority = _task8_authority(mapping, source_manifest)
    mapping["support_recovery"]["pattern_material_partition"][
        "hub_attachment_face_ids_by_instance"
    ] = []
    mapping["task8_reconstruction_evidence_hash_sha256"] = (
        task8_reconstruction_evidence_hash(
            mapping["support_recovery"],
            mapping["periodic_provenance"],
            source_manifest["sha256"],
        )
    )

    with pytest.raises(PatternReconstructionError) as raised:
        validate_mapped_pattern_reconstruction(
            graph,
            mapping,
            source_manifest,
            task8_recovery_authority=task8_authority,
        )

    assert raised.value.reason == "v116_task8_evidence_untrusted"


def test_open_graph_rejects_false_material_shroud_role_or_area():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    support["material_shroud"] = {
        "status": "PASS",
        "semantic_role": "closed_shroud",
        "material": True,
    }
    _seal_support_evidence(
        support, trusted_authority["source_topology_manifest"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_open_material_shroud_forbidden"


def test_closed_graph_rejects_missing_authenticated_finite_thickness():
    graph = copy.deepcopy(_runtime_graph("radial_closed_reference_v1_1"))
    periodic, support, trusted_authority = _closed_case(graph)
    support["material_shroud"].pop("finite_thickness")
    _seal_support_evidence(
        support, trusted_authority["source_topology_manifest"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_closed_shroud_thickness_missing"


def test_closed_graph_rejects_missing_topology_support_provenance():
    graph = copy.deepcopy(_runtime_graph("radial_closed_reference_v1_1"))
    periodic, support, trusted_authority = _closed_case(graph)
    support["material_shroud"]["blade_attachment"].pop("provenance")

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_material_provenance_missing"


def test_support_payload_mutation_rejects_well_formed_stale_nested_digest():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    support["hub_support"]["material"] = False
    _seal_support_record(
        support, trusted_authority["source_topology_manifest"]
    )
    assert len(
        support["hub_support"]["provenance"]["evidence_digest_sha256"]
    ) == 64

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_material_provenance_missing"


def test_well_formed_top_level_support_digest_mutation_is_recomputed():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    provenance = support["provenance"]
    provenance["evidence_digest_sha256"] = _different_sha256(
        provenance["evidence_digest_sha256"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_material_provenance_missing"


def test_resigned_blade_face_as_hub_fails_independent_support_partition():
    graph = copy.deepcopy(_runtime_graph("public_rocket_turbopump_inducer_v1_1"))
    periodic, support, trusted_authority = _open_case(graph)
    blade_face_id = periodic["main"]["instances"][1]["source_face_ids"][0]
    support["hub_support"]["source_face_ids"] = [blade_face_id]
    support["hub_support"]["provenance"]["source_entity_ids"] = [blade_face_id]
    _seal_support_evidence(
        support, trusted_authority["source_topology_manifest"]
    )

    with pytest.raises(PatternReconstructionError) as raised:
        _validate_case(graph, periodic, support, trusted_authority)

    assert raised.value.reason == "v116_material_provenance_missing"
