from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
ONTOLOGY_ROOT = PACKAGE_ROOT / "ontology" / "impeller" / "v0_2"
DSL_ROOT = PACKAGE_ROOT / "dsl" / "impeller" / "axisymmetric_throughflow_radial_bladed" / "v0_2"


@dataclass(frozen=True)
class ImpellerDslBundle:
    slice: dict[str, Any]
    entities: dict[str, Any]
    relations: dict[str, Any]
    shape_control_schema: dict[str, Any]
    validity_contracts: dict[str, Any]
    loss_schema: dict[str, Any]
    schema: dict[str, Any]
    constructors: dict[str, dict[str, Any]]
    shape_controls: dict[str, Any]
    presets: dict[str, dict[str, Any]]
    aliases: dict[str, str]


def load_impeller_dsl_bundle() -> ImpellerDslBundle:
    constructors = {
        "axisymmetric_throughflow_radial_bladed.open": _read_json(
            DSL_ROOT / "constructors" / "open_impeller.json"
        ),
        "axisymmetric_throughflow_radial_bladed.closed": _read_json(
            DSL_ROOT / "constructors" / "closed_impeller.json"
        ),
    }
    presets = {
        "radial_open_reference": _read_json(DSL_ROOT / "presets" / "radial_open_reference.json"),
        "radial_closed_reference": _read_json(DSL_ROOT / "presets" / "radial_closed_reference.json"),
    }
    aliases = _read_json(DSL_ROOT / "aliases.json")["legacy_preset_aliases"]
    bundle = ImpellerDslBundle(
        slice=_read_json(ONTOLOGY_ROOT / "slice.json"),
        entities=_read_json(ONTOLOGY_ROOT / "entities.json"),
        relations=_read_json(ONTOLOGY_ROOT / "relations.json"),
        shape_control_schema=_read_json(ONTOLOGY_ROOT / "shape_control_schema.json"),
        validity_contracts=_read_json(ONTOLOGY_ROOT / "validity_contracts.json"),
        loss_schema=_read_json(ONTOLOGY_ROOT / "loss_schema.json"),
        schema=_read_json(DSL_ROOT / "schema.json"),
        constructors=constructors,
        shape_controls=_read_json(DSL_ROOT / "shape_controls" / "default_shape_controls.json"),
        presets=presets,
        aliases=aliases,
    )
    _validate_bundle(bundle)
    return bundle


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_bundle(bundle: ImpellerDslBundle) -> None:
    family = "AxisymmetricThroughflowRadialBladedImpeller"
    if bundle.slice["constructor_family"] != family:
        raise ValueError("impeller ontology slice constructor family mismatch")
    if bundle.schema["constructor_family"] != family:
        raise ValueError("impeller DSL schema constructor family mismatch")
    if bundle.shape_control_schema["default_stage"] != 1:
        raise ValueError("impeller v0.2 shape control must default to stage 1")
    if "hub_meridional_profile" not in bundle.shape_controls["target_entities"]:
        raise ValueError("default shape controls must include hub_meridional_profile")
    _validate_shape_control_policies(bundle)
    for constructor_id, constructor in bundle.constructors.items():
        if constructor["constructor_id"] != constructor_id:
            raise ValueError(f"constructor id mismatch: {constructor_id}")
        missing = set(bundle.schema["required_sections"]) - set(constructor)
        if missing:
            raise ValueError(f"constructor {constructor_id} missing sections: {sorted(missing)}")
        if constructor["shape_control"]["shape_control_ref"] != "shape_controls/default_shape_controls.json":
            raise ValueError(f"constructor {constructor_id} references unsupported shape control policy")
    for preset_id, preset in bundle.presets.items():
        if preset["preset_id"] != preset_id:
            raise ValueError(f"preset id mismatch: {preset_id}")
        if preset["constructor_id"] not in bundle.constructors:
            raise ValueError(f"preset {preset_id} references unknown constructor")


def _validate_shape_control_policies(bundle: ImpellerDslBundle) -> None:
    target_entities = set(bundle.shape_controls["target_entities"])
    policy_entities = set(bundle.shape_controls["policies"])
    missing = target_entities - policy_entities
    if missing:
        raise ValueError(f"default shape controls missing policies: {sorted(missing)}")
    allowed = set(bundle.shape_control_schema["allowed_representations"])
    for target_entity, policy in bundle.shape_controls["policies"].items():
        if policy["target_entity"] != target_entity:
            raise ValueError(f"shape-control target mismatch: {target_entity}")
        if policy["representation"] not in allowed:
            raise ValueError(f"unsupported representation for {target_entity}: {policy['representation']}")
