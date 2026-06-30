from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
ONTOLOGY_BASE = PACKAGE_ROOT / "ontology" / "impeller"
DSL_BASE = PACKAGE_ROOT / "dsl" / "impeller" / "axisymmetric_throughflow_radial_bladed"
DEFAULT_DSL_VERSION = "v0_2"


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


def load_impeller_dsl_bundle(version: str = DEFAULT_DSL_VERSION) -> ImpellerDslBundle:
    ontology_root = ONTOLOGY_BASE / version
    dsl_root = DSL_BASE / version
    fallback_ontology_root = ONTOLOGY_BASE / DEFAULT_DSL_VERSION
    fallback_dsl_root = DSL_BASE / DEFAULT_DSL_VERSION
    if not dsl_root.exists():
        raise ValueError(f"unknown impeller DSL version: {version}")

    constructors = _load_json_directory_by_id(dsl_root / "constructors", "constructor_id")
    presets = _load_json_directory_by_id(dsl_root / "presets", "preset_id")
    aliases = _read_json(dsl_root / "aliases.json")["legacy_preset_aliases"]
    shape_controls = _read_json(dsl_root / "shape_controls" / "default_shape_controls.json")
    if "policies" not in shape_controls:
        carried_forward = _read_json(fallback_dsl_root / "shape_controls" / "default_shape_controls.json")
        shape_controls = {
            **shape_controls,
            "policies": carried_forward["policies"],
        }
    bundle = ImpellerDslBundle(
        slice=_read_json_with_fallback(ontology_root / "slice.json", fallback_ontology_root / "slice.json"),
        entities=_read_json_with_fallback(ontology_root / "entities.json", fallback_ontology_root / "entities.json"),
        relations=_read_json_with_fallback(ontology_root / "relations.json", fallback_ontology_root / "relations.json"),
        shape_control_schema=_read_json_with_fallback(
            ontology_root / "shape_control_schema.json",
            fallback_ontology_root / "shape_control_schema.json",
        ),
        validity_contracts=_read_json_with_fallback(
            ontology_root / "validity_contracts.json",
            fallback_ontology_root / "validity_contracts.json",
        ),
        loss_schema=_read_json_with_fallback(
            ontology_root / "loss_schema.json",
            fallback_ontology_root / "loss_schema.json",
        ),
        schema=_read_json(dsl_root / "schema.json"),
        constructors=constructors,
        shape_controls=shape_controls,
        presets=presets,
        aliases=aliases,
    )
    _validate_bundle(bundle)
    return bundle


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_with_fallback(path: Path, fallback_path: Path) -> dict[str, Any]:
    return _read_json(path if path.exists() else fallback_path)


def _load_json_directory_by_id(path: Path, id_field: str) -> dict[str, dict[str, Any]]:
    items = {}
    for item_path in sorted(path.glob("*.json")):
        item = _read_json(item_path)
        items[item[id_field]] = item
    return items


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
    material_domain_entities = set(bundle.shape_controls.get("material_domain_controls", {}))
    missing = target_entities - policy_entities - material_domain_entities
    if missing:
        raise ValueError(f"default shape controls missing policies: {sorted(missing)}")
    allowed = set(bundle.shape_control_schema["allowed_representations"])
    for target_entity, policy in bundle.shape_controls["policies"].items():
        if policy["target_entity"] != target_entity:
            raise ValueError(f"shape-control target mismatch: {target_entity}")
        if policy["representation"] not in allowed:
            raise ValueError(f"unsupported representation for {target_entity}: {policy['representation']}")
