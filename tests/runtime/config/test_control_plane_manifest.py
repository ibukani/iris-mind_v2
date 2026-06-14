"""iris-control-plane.toml manifestの内容・存在・読み込みを検証する。"""

from __future__ import annotations

from pathlib import Path
import tomllib
from typing import TypeGuard

from iris.runtime.config import load_runtime_config

_DENY = "deny"


def test_manifest_parses_successfully() -> None:
    """iris-control-plane.tomlが有効なTOMLとしてパースできる。"""
    manifest = _load_manifest()
    assert manifest["schema_version"] == 2
    assert manifest["id"] == "iris-mind"


def test_manifest_contains_runtime_editable_config() -> None:
    """Runtime editable configがiris-control-plane.tomlに宣言されている。"""
    configs = _editable_configs()
    runtime = _find_editable_config(configs, "runtime")
    assert runtime is not None, "runtime editable_configs entry is missing"


def test_runtime_editable_config_path() -> None:
    """Runtime editable configのpathは.iris/config/runtime.toml。"""
    runtime = _find_editable_config(_editable_configs(), "runtime")
    assert runtime is not None
    assert runtime["path"] == ".iris/config/runtime.toml"


def test_runtime_editable_config_template() -> None:
    """Runtime editable configのtemplateは.iris/config/runtime.example.toml。"""
    runtime = _find_editable_config(_editable_configs(), "runtime")
    assert runtime is not None
    assert runtime["template"] == ".iris/config/runtime.example.toml"


def test_runtime_editable_config_schema_manifest() -> None:
    """Runtime editable configはschema_manifestを持つ。"""
    runtime = _find_editable_config(_editable_configs(), "runtime")
    assert runtime is not None
    assert runtime["schema_manifest"] == ".iris/control-plane/runtime-config.schema.json"


def test_runtime_editable_config_format() -> None:
    """Runtime editable configのformatはtoml。"""
    runtime = _find_editable_config(_editable_configs(), "runtime")
    assert runtime is not None
    assert runtime["format"] == "toml"


def test_runtime_editable_config_schema() -> None:
    """Runtime editable configのschemaはiris-mind.runtime.v1。"""
    runtime = _find_editable_config(_editable_configs(), "runtime")
    assert runtime is not None
    assert runtime["schema"] == "iris-mind.runtime.v1"


def test_runtime_editable_config_restart_required() -> None:
    """Runtime editable configはrestart_required=true。"""
    runtime = _find_editable_config(_editable_configs(), "runtime")
    assert runtime is not None
    assert runtime["restart_required"] is True


def test_runtime_editable_config_secret_policy() -> None:
    """Runtime editable configのsecret_policyはdeny。"""
    runtime = _find_editable_config(_editable_configs(), "runtime")
    assert runtime is not None
    assert runtime["secret_policy"] == _DENY


def test_runtime_editable_config_provision() -> None:
    """Runtime editable configのprovisionはcopy_if_missing。"""
    runtime = _find_editable_config(_editable_configs(), "runtime")
    assert runtime is not None
    assert runtime["provision"] == "copy_if_missing"


def test_runtime_example_file_exists() -> None:
    """.iris/config/runtime.example.tomlが存在する。"""
    path = _repo_path(".iris/config/runtime.example.toml")
    assert path.is_file(), f"runtime example not found at {path}"


def test_schema_manifest_file_exists() -> None:
    """.iris/control-plane/runtime-config.schema.jsonが存在する。"""
    path = _repo_path(".iris/control-plane/runtime-config.schema.json")
    assert path.is_file(), f"schema manifest not found at {path}"


def test_runtime_example_loads_through_loader() -> None:
    """runtime.example.tomlがload_runtime_configをパスする。"""
    path = _repo_path(".iris/config/runtime.example.toml")
    config = load_runtime_config(path, env={})
    assert config is not None


def _load_manifest() -> dict[str, object]:
    path = _repo_path("iris-control-plane.toml")
    raw: object = tomllib.loads(path.read_text(encoding="utf-8"))
    if _is_dict(raw):
        return raw
    msg = "iris-control-plane.toml must be a TOML table"
    raise AssertionError(msg)


def _editable_configs() -> list[dict[str, object]]:
    manifest = _load_manifest()
    configs_raw: object = manifest.get("editable_configs", ())
    if not _is_list(configs_raw):
        configs_raw = []
    items: list[object] = list(configs_raw)
    dict_items: list[dict[str, object]] = [c for c in items if _is_dict(c)]
    return dict_items


def _is_dict(value: object) -> TypeGuard[dict[str, object]]:
    """Narrow object to dict[str, object] for item iteration.

    Runtime check uses isinstance(dict) which erases type parameters, so the
    narrowed type uses the widest compatible parameter types.

    Returns:
        True if value is a dict, narrowing to the widened type.
    """
    return isinstance(value, dict)


def _is_list(value: object) -> TypeGuard[list[object]]:
    """Narrow object to list[object] for item iteration.

    Returns:
        True if value is a list, narrowing to the widened type.
    """
    return isinstance(value, list)


def _find_editable_config(
    configs: list[dict[str, object]],
    config_id: str,
) -> dict[str, object] | None:
    for config in configs:
        if config.get("id") == config_id:
            return config
    return None


def _repo_path(relative_path: str) -> Path:
    return Path(__file__).resolve().parents[3] / relative_path
