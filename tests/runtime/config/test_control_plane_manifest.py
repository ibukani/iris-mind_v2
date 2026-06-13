"""iris-control-plane.toml manifestの内容・存在・読み込みを検証する。"""

from __future__ import annotations

from pathlib import Path
import tomllib
from typing import Any

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


def _load_manifest() -> dict[str, Any]:
    path = _repo_path("iris-control-plane.toml")
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _editable_configs() -> list[dict[str, Any]]:
    manifest = _load_manifest()
    configs = manifest.get("editable_configs", [])
    assert isinstance(configs, list)
    validated: list[dict[str, Any]] = []
    for c in configs:
        assert isinstance(c, dict)
        validated.append(c)
    return validated


def _find_editable_config(
    configs: list[dict[str, Any]],
    config_id: str,
) -> dict[str, Any] | None:
    for config in configs:
        if config.get("id") == config_id:
            return config
    return None


def _repo_path(relative_path: str) -> Path:
    return Path(__file__).resolve().parents[3] / relative_path
