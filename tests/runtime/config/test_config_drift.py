"""Runtime config drift tests."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import tomllib
from typing import TYPE_CHECKING, TypeGuard

from iris.runtime.config import (
    default_runtime_config,
    load_runtime_config,
    runtime_config_specs,
    runtime_config_specs_for_version,
)
from iris.runtime.config.model_slots import model_slot_specs
from iris.runtime.config.schema import render_runtime_config_schema

if TYPE_CHECKING:
    from collections.abc import Mapping


def test_compact_template_paths_are_known_v2_paths() -> None:
    """Compact templateはv2 user configの既知pathだけを含む。"""
    example_paths = _toml_leaf_paths(_full_example_path())
    known_paths = {spec.path for spec in runtime_config_specs_for_version(2) if spec.toml}
    assert example_paths <= known_paths


def test_runtime_defaults_match_config_spec() -> None:
    """Typed runtime defaults match ConfigSpec defaults."""
    defaults = _runtime_defaults()
    spec_defaults = {spec.path: spec.default for spec in runtime_config_specs()}

    assert defaults == spec_defaults


def test_model_slot_specs_match_runtime_defaults() -> None:
    """Shared model slot specs stay aligned with runtime defaults."""
    slot_specs = model_slot_specs()
    default_models = default_runtime_config().models

    assert tuple(spec.name for spec in slot_specs) == (
        "default_chat",
        "fast_judge",
        "reasoning",
    )
    assert tuple(spec.default_max_output_tokens for spec in slot_specs) == (
        default_models.default_chat.max_output_tokens,
        default_models.fast_judge.max_output_tokens,
        default_models.reasoning.max_output_tokens,
    )


def test_full_example_values_are_applied_by_runtime_parser() -> None:
    """Canonical example keys are applied by the runtime parser."""
    config_values = _flatten_mapping(
        asdict(load_runtime_config(_full_example_path(), env={})),
    )
    example_values = _flatten_mapping(
        tomllib.loads(_full_example_path().read_text(encoding="utf-8")),
    )

    assert {path: config_values[path] for path in example_values} == example_values


def test_config_spec_env_names_are_unique() -> None:
    """ConfigSpec environment variable names are unique."""
    env_names = [spec.env for spec in runtime_config_specs() if spec.env is not None]

    assert len(env_names) == len(set(env_names))


def test_secret_specs_are_absent_from_full_example() -> None:
    """Secret fields are excluded from the canonical example."""
    example_paths = _toml_leaf_paths(_full_example_path())
    secret_paths = {spec.path for spec in runtime_config_specs() if spec.secret}

    assert example_paths.isdisjoint(secret_paths)


def test_control_plane_manifest_matches_config_spec() -> None:
    """Committed schemaはConfigSpecからの生成結果と一致する。"""
    path = _repo_path(".iris/control-plane/runtime-config.schema.json")
    assert path.read_text(encoding="utf-8") == render_runtime_config_schema()


def test_generated_schema_excludes_secret_fields() -> None:
    """Secret field は generated public schema に含まれない。"""
    schema_text = render_runtime_config_schema()
    schema = json.loads(schema_text)
    all_paths = _json_schema_leaf_paths(schema.get("properties", {}), "")
    secret_paths = {spec.path for spec in runtime_config_specs_for_version(2) if spec.secret}
    assert secret_paths, "No secret specs found; test cannot validate exclusion"
    assert all_paths.isdisjoint(secret_paths), (
        f"Secret fields leaked into public schema: {all_paths & secret_paths}"
    )


def _json_schema_leaf_paths(
    properties: Mapping[str, object],
    prefix: str,
) -> set[str]:
    """JSON Schema properties から leaf path の集合を返す。

    Returns:
        leaf property path の集合。
    """
    paths: set[str] = set()
    for key, value in properties.items():
        path = f"{prefix}.{key}" if prefix else key
        if _is_dict(value) and "properties" in value:
            child_props = value.get("properties")
            if _is_dict(child_props):
                paths.update(_json_schema_leaf_paths(child_props, path))
        else:
            paths.add(path)
    return paths


def _runtime_defaults() -> dict[str, str | int | float | bool | None]:
    return _flatten_mapping(asdict(default_runtime_config()))


def _flatten_mapping(
    table: Mapping[str, object],
    prefix: str = "",
) -> dict[str, str | int | float | bool | None]:
    values: dict[str, str | int | float | bool | None] = {}
    for key, value in table.items():
        path = f"{prefix}.{key}" if prefix else key
        if _is_dict(value):
            assert all(isinstance(k, str) for k in value)
            values.update(_flatten_mapping(value, path))
        elif isinstance(value, (str, int, float, bool)) or value is None:
            values[path] = value
        else:
            msg = f"Unsupported runtime config value at {path}: {type(value).__name__}"
            raise AssertionError(msg)
    return values


def _toml_leaf_paths(path: Path) -> set[str]:
    document_raw: object = tomllib.loads(path.read_text(encoding="utf-8"))
    document = _as_mapping(document_raw)
    return _mapping_leaf_paths(document, "")


def _as_mapping(value: object) -> Mapping[str, object]:
    if _is_dict(value):
        return value
    return {}


def _is_dict(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow object to dict[str, object].

    Returns:
        True if value is a dict.
    """
    return isinstance(value, dict)


def _mapping_leaf_paths(table: Mapping[str, object], prefix: str) -> set[str]:
    paths: set[str] = set()
    for key, value in table.items():
        path = f"{prefix}.{key}" if prefix else key
        if _is_dict(value):
            assert all(isinstance(k, str) for k in value)
            paths.update(_mapping_leaf_paths(value, path))
        else:
            paths.add(path)
    return paths


def _full_example_path() -> Path:
    return _repo_path("iris/runtime/config/templates/runtime.example.toml")


def _repo_path(relative_path: str) -> Path:
    return Path(__file__).resolve().parents[3] / relative_path
