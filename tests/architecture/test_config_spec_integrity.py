"""Runtime config default と ConfigFieldSpec の drift を検出する。"""

from __future__ import annotations

from dataclasses import fields, is_dataclass

from iris.runtime.config import default_runtime_config
from iris.runtime.config.spec import ConfigDefault, runtime_config_specs

type ConfigLeaf = ConfigDefault


def _config_leaf_paths(prefix: str, value: object) -> dict[str, ConfigLeaf]:
    if is_dataclass(value):
        leaves: dict[str, ConfigLeaf] = {}
        for field in fields(value):
            child_prefix = f"{prefix}.{field.name}" if prefix else field.name
            leaves.update(_config_leaf_paths(child_prefix, getattr(value, field.name)))
        return leaves
    if isinstance(value, (str, int, float, bool)) or value is None:
        return {prefix: value}
    message = f"Unsupported runtime config leaf at {prefix}: {type(value).__name__}"
    raise AssertionError(message)


def test_config_specs_match_default_runtime_config() -> None:
    """ConfigFieldSpec.path/default は default_runtime_config と一致する。"""
    defaults = _config_leaf_paths("", default_runtime_config())
    specs = runtime_config_specs()
    spec_defaults = {spec.path: spec.default for spec in specs}

    assert set(spec_defaults) == set(defaults)
    mismatches = {
        path: (spec_defaults[path], defaults[path])
        for path in sorted(defaults)
        if spec_defaults[path] != defaults[path]
    }
    assert not mismatches


def test_config_specs_do_not_duplicate_env_names_or_cli_flags() -> None:
    """ConfigFieldSpec.env と cli は重複しない。"""
    specs = runtime_config_specs()
    env_names = [spec.env for spec in specs if spec.env is not None]
    cli_flags = [spec.cli for spec in specs if spec.cli is not None]
    assert len(env_names) == len(set(env_names))
    assert len(cli_flags) == len(set(cli_flags))
