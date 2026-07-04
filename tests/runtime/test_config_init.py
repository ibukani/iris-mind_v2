"""Runtime config initialization tests."""

from __future__ import annotations

import sys
import tomllib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from iris.runtime.config import ConfigError, load_runtime_config
from iris.runtime.config import init as config_init
from iris.runtime.config.init import init_runtime_config, runtime_config_template
from iris.runtime.server import main

_TEMPLATE = """[config]
version = 2

[models.default_chat]
provider = "fake"
model = "fake-llm"
"""


def _write_example(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the packaged template reader with isolated template content."""
    (tmp_path / ".iris/config").mkdir(parents=True)
    monkeypatch.setattr(config_init, "_read_template_resource", lambda: _TEMPLATE)


def test_init_runtime_config_creates_default_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Creates runtime.toml from the example template."""
    _write_example(tmp_path, monkeypatch)
    target_path = tmp_path / ".iris/config/runtime.toml"

    result = init_runtime_config(path=target_path)

    assert result.path == target_path
    assert result.created is True
    assert result.overwritten is False
    assert target_path.read_text(encoding="utf-8") == _TEMPLATE


def test_committed_init_template_is_compact_and_loadable(tmp_path: Path) -> None:
    """Canonical templateは通常利用向けの短いv2 config。"""
    target_path = tmp_path / "runtime.toml"

    init_runtime_config(path=target_path)
    document = tomllib.loads(target_path.read_text(encoding="utf-8"))
    config = load_runtime_config(target_path, env={})

    assert set(document) == {"config", "models", "prompt_budget", "model_call_budget", "safety"}
    assert document["safety"]["high_risk_context_detection_enabled"] is False
    assert config.config.version == 2
    assert config.safety.high_risk_context_detection_enabled is False


def test_runtime_config_template_returns_packaged_compact_template() -> None:
    """Packaged templateは通常利用に必要なsectionだけを含む。"""
    document = tomllib.loads(runtime_config_template())

    assert set(document) == {"config", "models", "prompt_budget", "model_call_budget", "safety"}
    assert document["safety"]["high_risk_context_detection_enabled"] is False


def test_init_runtime_config_creates_parent_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Creates parent directories for a custom target path."""
    _write_example(tmp_path, monkeypatch)
    target_path = tmp_path / "nested/config/local.toml"

    result = init_runtime_config(path=target_path)

    assert result.created is True
    assert target_path.read_text(encoding="utf-8") == _TEMPLATE


def test_init_runtime_config_does_not_overwrite_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing target remains unchanged without force."""
    _write_example(tmp_path, monkeypatch)
    target_path = tmp_path / ".iris/config/runtime.toml"
    target_path.write_text("existing = true\n", encoding="utf-8")

    result = init_runtime_config(path=target_path)

    assert result.created is False
    assert result.overwritten is False
    assert target_path.read_text(encoding="utf-8") == "existing = true\n"


def test_init_runtime_config_force_overwrites_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force replaces the existing target file."""
    _write_example(tmp_path, monkeypatch)
    target_path = tmp_path / ".iris/config/runtime.toml"
    target_path.write_text("existing = true\n", encoding="utf-8")

    result = init_runtime_config(path=target_path, force=True)

    assert result.created is False
    assert result.overwritten is True
    assert target_path.read_text(encoding="utf-8") == _TEMPLATE


def test_init_runtime_config_print_only_does_not_write_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI --print writes the template to stdout without creating a target."""
    _write_example(tmp_path, monkeypatch)
    target_path = tmp_path / ".iris/config/runtime.toml"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["server", "init-config", "--path", str(target_path), "--print"],
    )

    main()

    assert capsys.readouterr().out == runtime_config_template()
    assert not target_path.exists()


def test_init_runtime_config_missing_example_raises_config_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing example template raises ConfigError with a clear message."""
    del tmp_path

    def _raise_missing_template() -> str:
        raise FileNotFoundError

    monkeypatch.setattr(config_init, "_read_template_resource", _raise_missing_template)

    with pytest.raises(ConfigError, match="Runtime config template does not exist"):
        runtime_config_template()


def test_init_config_cli_reports_created_and_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI reports created and already-exists states with exit-code success."""
    _write_example(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["server", "init-config"])

    main()

    assert capsys.readouterr().out == (
        "Runtime config created: .iris/config/runtime.toml\n"
        "Iris-Mind will load this file automatically on normal startup.\n"
        "Use --config PATH to run with a different config file.\n"
    )

    main()

    assert capsys.readouterr().out == (
        "Runtime config already exists: .iris/config/runtime.toml\n"
        "Iris-Mind will load this file automatically on normal startup.\n"
        "Use --config PATH to run with a different config file.\n"
    )


def test_missing_default_config_loading_uses_defaults(tmp_path: Path) -> None:
    """Config loading uses defaults when no default file exists."""
    config = load_runtime_config(None, env={}, cwd=tmp_path)
    missing_path = tmp_path / "missing.toml"

    assert config.models.default_chat.provider == "fake"
    with pytest.raises(ConfigError):
        load_runtime_config(missing_path, env={})


def test_init_config_output_is_loaded_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """init-config creates the project-local config loaded by normal startup."""
    _write_example(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)

    init_runtime_config()
    config = load_runtime_config(None, env={}, cwd=tmp_path)

    assert config.models.default_chat.provider == "fake"
    assert config.models.default_chat.model == "fake-llm"
