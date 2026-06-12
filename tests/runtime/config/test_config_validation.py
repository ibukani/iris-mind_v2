"""Runtime config versioningとstrict key検証。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import ConfigError, load_runtime_config

if TYPE_CHECKING:
    from pathlib import Path


def test_missing_config_version_is_treated_as_version_one(tmp_path: Path) -> None:
    """version省略は後方互換としてv1扱いになる。"""
    config = load_runtime_config(_write(tmp_path, "[state]\nbackend = 'memory'\n"), env={})

    assert config.config.version == 1


def test_explicit_config_version_one_is_accepted(tmp_path: Path) -> None:
    """Version 1は受理される。"""
    config = load_runtime_config(_write(tmp_path, "[config]\nversion = 1\n"), env={})

    assert config.config.version == 1


def test_unsupported_config_version_is_rejected(tmp_path: Path) -> None:
    """未知versionは明確なConfigErrorになる。"""
    with pytest.raises(ConfigError, match="Unsupported runtime config version: 2"):
        load_runtime_config(_write(tmp_path, "[config]\nversion = 2\n"), env={})


def test_unsupported_config_version_is_reported_before_unknown_keys(
    tmp_path: Path,
) -> None:
    """Unsupported versionはfuture key検証より先に報告される。"""
    config_path = _write(
        tmp_path,
        """
        [config]
        version = 2

        [future_section]
        enabled = true
        """,
    )

    with pytest.raises(ConfigError, match="Unsupported runtime config version: 2"):
        load_runtime_config(config_path, env={})


def test_invalid_config_version_type_is_rejected(tmp_path: Path) -> None:
    """versionの型不一致はConfigErrorになる。"""
    with pytest.raises(ConfigError, match=r"config\.version.*integer"):
        load_runtime_config(_write(tmp_path, "[config]\nversion = '1'\n"), env={})


def test_invalid_config_version_type_is_rejected_before_key_validation(
    tmp_path: Path,
) -> None:
    """Version型不正はfuture key検証より先に報告される。"""
    config_path = _write(
        tmp_path,
        """
        [config]
        version = "2"

        [future_section]
        enabled = true
        """,
    )

    with pytest.raises(ConfigError, match=r"config\.version.*integer"):
        load_runtime_config(config_path, env={})


def test_config_section_must_be_table(tmp_path: Path) -> None:
    """Config sectionはversion読取前にtable形状を要求する。"""
    config_path = _write(tmp_path, 'config = "invalid"\n')

    with pytest.raises(ConfigError, match=r"config.*table"):
        load_runtime_config(config_path, env={})


def test_version_one_still_rejects_unknown_keys(tmp_path: Path) -> None:
    """Version 1ではstrict key検証を維持する。"""
    config_path = _write(
        tmp_path,
        """
        [config]
        version = 1

        [server]
        address = "localhost"
        """,
    )

    with pytest.raises(ConfigError, match=r"server\.address"):
        load_runtime_config(config_path, env={})


def test_safety_toml_is_applied(tmp_path: Path) -> None:
    """Safety sectionはTOMLからtyped configへ適用される。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            "[safety]\nmode = 'basic'\nmax_output_chars = 1200\n",
        ),
        env={},
    )

    assert config.safety.mode == "basic"
    assert config.safety.max_output_chars == 1200


def test_invalid_safety_mode_is_rejected(tmp_path: Path) -> None:
    """Safety modeはConfigSpecのallowed valuesに制限される。"""
    with pytest.raises(ConfigError, match="Allowed values: development, basic"):
        load_runtime_config(
            _write(tmp_path, "[safety]\nmode = 'disabled'\n"),
            env={},
        )


@pytest.mark.parametrize(
    ("content", "path"),
    [
        ("[unknown]\nvalue = 1\n", "unknown"),
        ("[server]\naddress = 'localhost'\n", "server.address"),
        ("[models.unknown]\nprovider = 'fake'\n", "models.unknown"),
        (
            "[models.default_chat]\nmax_tokens = 10\n",
            "models.default_chat.max_tokens",
        ),
    ],
)
def test_unknown_config_keys_are_rejected(
    tmp_path: Path,
    content: str,
    path: str,
) -> None:
    """未知section・slot・keyは黙って無視しない。"""
    config_path = _write(tmp_path, content)

    with pytest.raises(ConfigError, match=path):
        load_runtime_config(config_path, env={})


def test_unknown_key_error_suggests_close_spec_path(tmp_path: Path) -> None:
    """typoに近い正規keyを提示する。"""
    config_path = _write(
        tmp_path,
        "[models.default_chat]\nmax_tokens = 10\n",
    )

    with pytest.raises(ConfigError, match=r"models\.default_chat\.max_output_tokens"):
        load_runtime_config(config_path, env={})


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "runtime.toml"
    path.write_text(content, encoding="utf-8")
    return path
