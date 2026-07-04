"""Control Plane向け生成schema。"""

from __future__ import annotations

import json
from pathlib import Path

from iris.runtime.config.spec import ConfigFieldSpec, runtime_config_specs_for_version

SCHEMA_PATH = Path(".iris/control-plane/runtime-config.schema.json")


def render_runtime_config_schema() -> str:
    """v2 user config schemaを決定的なJSONとして生成する。

    Returns:
        compact JSON schema文字列。
    """
    properties: dict[str, object] = {}
    for spec in runtime_config_specs_for_version(2):
        _add_property(properties, spec.path.split("."), _field_json_schema(spec))
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
        "x-iris-version": 2,
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"


def _add_property(
    properties: dict[str, object],
    parts: list[str],
    leaf: dict[str, object],
) -> None:
    key = parts[0]
    if len(parts) == 1:
        properties[key] = leaf
        return
    child = properties.setdefault(
        key,
        {"type": "object", "properties": {}, "additionalProperties": False},
    )
    if not isinstance(child, dict):
        msg = f"Schema path collides at {key}"
        raise TypeError(msg)
    child_properties = child["properties"]
    if not isinstance(child_properties, dict):
        msg = f"Schema properties are invalid at {key}"
        raise TypeError(msg)
    _add_property(child_properties, parts[1:], leaf)


def _field_json_schema(spec: ConfigFieldSpec) -> dict[str, object]:
    type_map = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "enum": "string",
        "optional_str": ["string", "null"],
        "optional_int": ["integer", "null"],
        "optional_float": ["number", "null"],
    }
    schema: dict[str, object] = {
        "type": type_map[spec.value_type.value],
        "description": spec.description,
        "default": spec.default,
        "x-iris-env": spec.env,
        "x-iris-secret": spec.secret,
        "x-iris-editable": spec.control_plane_editable,
        "x-iris-advanced": spec.path.startswith("advanced."),
    }
    if spec.allowed_values:
        schema["enum"] = list(spec.allowed_values)
    return schema


def write_runtime_config_schema(path: Path = SCHEMA_PATH) -> None:
    """生成schemaを書き出す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_runtime_config_schema(), encoding="utf-8")
