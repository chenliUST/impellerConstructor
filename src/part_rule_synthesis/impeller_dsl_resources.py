from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parent
ONTOLOGY_BASE = PACKAGE_ROOT / "ontology" / "impeller"
DSL_BASE = PACKAGE_ROOT / "dsl" / "impeller" / "axisymmetric_throughflow_radial_bladed"
DEFAULT_DSL_VERSION = "v0_2"
SUPPORTED_V07_DEFAULT_TREATMENTS = {"none", "chamfer", "fillet"}


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
    simulation_views: dict[str, dict[str, Any]] = field(default_factory=dict)
    simulation_view_refs: dict[str, str] = field(default_factory=dict)
    export_contracts: dict[str, dict[str, Any]] = field(default_factory=dict)
    export_contract_refs: dict[str, str] = field(default_factory=dict)


def load_impeller_dsl_bundle(version: str = DEFAULT_DSL_VERSION) -> ImpellerDslBundle:
    ontology_root = ONTOLOGY_BASE / version
    dsl_root = DSL_BASE / version
    fallback_ontology_root = _fallback_version_root(ONTOLOGY_BASE, version)
    fallback_dsl_root = DSL_BASE / DEFAULT_DSL_VERSION
    if not dsl_root.exists():
        raise ValueError(f"unknown impeller DSL version: {version}")

    constructors = _load_json_directory_by_id(dsl_root / "constructors", "constructor_id")
    presets = _load_json_directory_by_id(dsl_root / "presets", "preset_id")
    aliases = _load_aliases(dsl_root / "aliases.json")
    simulation_views, simulation_view_refs = (
        _load_simulation_views(dsl_root / "simulation_views")
        if (dsl_root / "simulation_views").exists()
        else ({}, {})
    )
    export_contracts, export_contract_refs = (
        _load_export_contracts(dsl_root / "export_contracts")
        if (dsl_root / "export_contracts").exists()
        else ({}, {})
    )
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
        simulation_views=simulation_views,
        simulation_view_refs=simulation_view_refs,
        export_contracts=export_contracts,
        export_contract_refs=export_contract_refs,
    )
    _validate_bundle(bundle)
    return bundle


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_with_fallback(path: Path, fallback_path: Path) -> dict[str, Any]:
    if path.exists():
        return _read_json(path)
    if fallback_path.exists():
        return _read_json(fallback_path)
    return _read_json(ONTOLOGY_BASE / DEFAULT_DSL_VERSION / path.name)


def _load_aliases(path: Path) -> dict[str, str]:
    aliases = _read_json(path)
    return aliases.get("legacy_preset_aliases", aliases)


def _fallback_version_root(base: Path, version: str) -> Path:
    available = sorted((path for path in base.glob("v*") if path.is_dir()), key=lambda path: _version_key(path.name))
    previous = [
        path
        for path in available
        if _version_key(path.name) <= _version_key(version)
        and all((path / name).exists() for name in ["slice.json", "entities.json", "relations.json"])
    ]
    return previous[-1] if previous else base / DEFAULT_DSL_VERSION


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.removeprefix("v").split("_"))


def _load_json_directory_by_id(path: Path, id_field: str) -> dict[str, dict[str, Any]]:
    items = {}
    for item_path in sorted(path.glob("*.json")):
        item = _read_json(item_path)
        items[item[id_field]] = item
    return items


def _load_simulation_views(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    views = {}
    refs = {}
    for item_path in sorted(path.glob("*.json")):
        item = _read_json(item_path)
        view_id = item["view_id"]
        views[view_id] = item
        refs[f"{path.name}/{item_path.name}"] = view_id
    return views, refs


def _load_export_contracts(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    contracts = {}
    refs = {}
    for item_path in sorted(path.glob("*.json")):
        item = _read_json(item_path)
        contract_id = item["contract_id"]
        contracts[contract_id] = item
        refs[f"{path.name}/{item_path.name}"] = contract_id
    return contracts, refs


def _validate_bundle(bundle: ImpellerDslBundle) -> None:
    family = "AxisymmetricThroughflowRadialBladedImpeller"
    if bundle.slice["constructor_family"] != family:
        raise ValueError("impeller ontology slice constructor family mismatch")
    if bundle.schema["constructor_family"] != family:
        raise ValueError("impeller DSL schema constructor family mismatch")
    if bundle.schema["dsl_version"] in {"0.2", "0.3"} and bundle.shape_control_schema["default_stage"] != 1:
        raise ValueError("impeller v0.2/v0.3 shape control must default to stage 1")
    if bundle.schema["dsl_version"] in {"0.4", "0.5", "0.6", "0.7"} and "design_space" not in bundle.shape_controls:
        raise ValueError("impeller v0.4+ shape controls must include design_space")
    if "hub_meridional_profile" not in bundle.shape_controls["target_entities"]:
        raise ValueError("default shape controls must include hub_meridional_profile")
    if "policies" in bundle.shape_controls:
        _validate_shape_control_policies(bundle)
    for constructor_id, constructor in bundle.constructors.items():
        if constructor["constructor_id"] != constructor_id:
            raise ValueError(f"constructor id mismatch: {constructor_id}")
        missing = set(bundle.schema["required_sections"]) - set(constructor)
        if missing:
            raise ValueError(f"constructor {constructor_id} missing sections: {sorted(missing)}")
        if constructor["shape_control"]["shape_control_ref"] != "shape_controls/default_shape_controls.json":
            raise ValueError(f"constructor {constructor_id} references unsupported shape control policy")
        _validate_constructor_simulation_view_refs(bundle, constructor_id, constructor)
        _validate_constructor_export_contract_refs(bundle, constructor_id, constructor)
    for preset_id, preset in bundle.presets.items():
        if preset["preset_id"] != preset_id:
            raise ValueError(f"preset id mismatch: {preset_id}")
        if preset["constructor_id"] not in bundle.constructors:
            raise ValueError(f"preset {preset_id} references unknown constructor")
    if bundle.schema["dsl_version"] == "0.7":
        _validate_v07_edge_family_contracts(bundle)


def _validate_v07_edge_family_contracts(bundle: ImpellerDslBundle) -> None:
    for constructor_id, constructor in bundle.constructors.items():
        edge_families = constructor.get("edge_families")
        if not edge_families:
            raise ValueError(f"constructor {constructor_id} missing required V0.7 edge_families")
        if not isinstance(edge_families, dict):
            raise ValueError(f"constructor {constructor_id} V0.7 edge_families must be an object")
        for edge_family_id, edge_family in edge_families.items():
            if not isinstance(edge_family, dict):
                raise ValueError(f"constructor {constructor_id} edge family {edge_family_id} must be an object")
            for field_name in ["default_treatment", "default_radius_parameter"]:
                if field_name not in edge_family:
                    raise ValueError(f"constructor {constructor_id} edge family {edge_family_id} missing {field_name}")
            default_treatment = edge_family["default_treatment"]
            if default_treatment not in SUPPORTED_V07_DEFAULT_TREATMENTS:
                raise ValueError(
                    f"constructor {constructor_id} edge family {edge_family_id} "
                    f"has unsupported default_treatment {default_treatment}"
                )

    for preset_id, preset in bundle.presets.items():
        constructor_id = preset["constructor_id"]
        constructor = bundle.constructors[constructor_id]
        parameter_values = preset.get("parameter_values", {})
        for edge_family_id, edge_family in constructor["edge_families"].items():
            radius_parameter = edge_family["default_radius_parameter"]
            if radius_parameter not in parameter_values:
                raise ValueError(
                    f"preset {preset_id} missing edge-family radius parameter {radius_parameter} "
                    f"for constructor {constructor_id} edge family {edge_family_id}"
                )


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


def _validate_constructor_simulation_view_refs(
    bundle: ImpellerDslBundle,
    constructor_id: str,
    constructor: dict[str, Any],
) -> None:
    for view_id, view in constructor.get("simulation_views", {}).items():
        view_ref = view.get("view_ref")
        if view_ref is None:
            continue
        if bundle.simulation_view_refs and view_ref not in bundle.simulation_view_refs:
            raise ValueError(f"constructor {constructor_id} simulation view ref unresolved: {view_ref}")
        resolved_view_id = bundle.simulation_view_refs.get(view_ref, view_id)
        if resolved_view_id not in bundle.simulation_views:
            raise ValueError(f"constructor {constructor_id} simulation view ref unresolved: {view_ref}")
        if resolved_view_id != view_id:
            raise ValueError(
                f"constructor {constructor_id} simulation view {view_id} ref resolves to {resolved_view_id}"
            )


def _validate_constructor_export_contract_refs(
    bundle: ImpellerDslBundle,
    constructor_id: str,
    constructor: dict[str, Any],
) -> None:
    for contract_id, contract in constructor.get("export_contracts", {}).items():
        contract_ref = contract.get("contract_ref")
        if contract_ref is None:
            continue
        if bundle.export_contract_refs and contract_ref not in bundle.export_contract_refs:
            raise ValueError(f"constructor {constructor_id} export contract ref unresolved: {contract_ref}")
        resolved_contract_id = bundle.export_contract_refs.get(contract_ref, contract_id)
        if resolved_contract_id not in bundle.export_contracts:
            raise ValueError(f"constructor {constructor_id} export contract ref unresolved: {contract_ref}")
        if resolved_contract_id != contract_id:
            raise ValueError(
                f"constructor {constructor_id} export contract {contract_id} ref resolves to {resolved_contract_id}"
            )
