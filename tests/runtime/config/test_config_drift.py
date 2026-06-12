"""Runtime configのspec・example・manifest drift検査。"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import tomllib
from typing import TypedDict, cast

from iris.runtime.config import default_runtime_config, load_runtime_config, runtime_config_specs


class _ManifestField(TypedDict):
    path: str
    type: str
    default: str | int | float | bool | None
    allowedValues: list[str]
    env: str | None
    secret: bool
    editable: bool
    description: str


class _Manifest(TypedDict):
    version: int
    fields: list[_ManifestField]


def test_full_example_and_spec_paths_match() -> None:
    """Canonical exampleのkeyはConfigSpecと双方向に一致する。"""
    example_paths = _toml_leaf_paths(_full_example_path())
    specs = runtime_config_specs()
    expected_example_paths = {spec.path for spec in specs if spec.toml and spec.example}

    assert example_paths == expected_example_paths


def test_runtime_defaults_match_config_spec() -> None:
    """Typed runtime defaultsはConfigSpec defaultsと一致する。"""
    defaults = _runtime_defaults()
    spec_defaults = {spec.path: spec.default for spec in runtime_config_specs()}

    assert defaults == spec_defaults


def test_full_example_values_are_applied_by_runtime_parser() -> None:
    """Canonical exampleの全keyがruntime configへ反映される。"""
    config_values = _flatten_mapping(
        cast(
            "dict[str, object]",
            asdict(load_runtime_config(_full_example_path(), env={})),
        )
    )
    example_values = _flatten_mapping(
        cast(
            "dict[str, object]",
            tomllib.loads(_full_example_path().read_text(encoding="utf-8")),
        )
    )

    assert {path: config_values[path] for path in example_values} == example_values


def test_config_spec_env_names_are_unique() -> None:
    """ConfigSpecのenv名は重複しない。"""
    env_names = [spec.env for spec in runtime_config_specs() if spec.env is not None]

    assert len(env_names) == len(set(env_names))


def test_secret_specs_are_absent_from_full_example() -> None:
    """Secret fieldはcanonical exampleに含めない。"""
    example_paths = _toml_leaf_paths(_full_example_path())
    secret_paths = {spec.path for spec in runtime_config_specs() if spec.secret}

    assert example_paths.isdisjoint(secret_paths)


def test_control_plane_manifest_matches_config_spec() -> None:
    """Control Plane manifestはConfigSpec metadataと一致する。"""
    manifest = _load_manifest()
    specs = runtime_config_specs()
    expected = [
        _ManifestField(
            path=spec.path,
            type=spec.value_type,
            default=spec.default,
            allowedValues=list(spec.allowed_values),
            env=spec.env,
            secret=spec.secret,
            editable=spec.control_plane_editable,
            description=spec.description,
        )
        for spec in specs
    ]

    assert manifest["version"] == 1
    assert manifest["fields"] == expected


def _runtime_defaults() -> dict[str, str | int | float | bool | None]:
    return _flatten_mapping(cast("dict[str, object]", asdict(default_runtime_config())))


def _flatten_mapping(
    table: dict[str, object],
    prefix: str = "",
) -> dict[str, str | int | float | bool | None]:
    values: dict[str, str | int | float | bool | None] = {}
    for key, value in table.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            values.update(_flatten_mapping(cast("dict[str, object]", value), path))
        elif isinstance(value, (str, int, float, bool)) or value is None:
            values[path] = value
        else:
            msg = f"Unsupported runtime config value at {path}: {type(value).__name__}"
            raise AssertionError(msg)
    return values


def _toml_leaf_paths(path: Path) -> set[str]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    return _mapping_leaf_paths(cast("dict[str, object]", document), "")


def _mapping_leaf_paths(table: dict[str, object], prefix: str) -> set[str]:
    paths: set[str] = set()
    for key, value in table.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            paths.update(_mapping_leaf_paths(cast("dict[str, object]", value), path))
        else:
            paths.add(path)
    return paths


def _load_manifest() -> _Manifest:
    text = _repo_path(".iris/control-plane/runtime-config.schema.json").read_text(encoding="utf-8")
    return cast("_Manifest", json.loads(text))


def _full_example_path() -> Path:
    return _repo_path(".iris/config/runtime.example.toml")


def _repo_path(relative_path: str) -> Path:
    return Path(__file__).resolve().parents[3] / relative_path
