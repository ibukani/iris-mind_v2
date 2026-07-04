"""Runtime config versioningとstrict key検証。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from iris.runtime.config import ConfigError, load_runtime_config

if TYPE_CHECKING:
    from pathlib import Path


def test_missing_config_version_uses_version_two(tmp_path: Path) -> None:
    """version省略時も現行v2として扱う。"""
    config = load_runtime_config(_write(tmp_path, "[state]\nbackend = 'memory'\n"), env={})

    assert config.config.version == 2


def test_explicit_config_version_two_is_accepted(tmp_path: Path) -> None:
    """Version 2は受理される。"""
    config = load_runtime_config(_write(tmp_path, "[config]\nversion = 2\n"), env={})

    assert config.config.version == 2


def test_unsupported_config_version_is_rejected(tmp_path: Path) -> None:
    """未知versionは明確なConfigErrorになる。"""
    with pytest.raises(ConfigError, match="Unsupported runtime config version: 1"):
        load_runtime_config(_write(tmp_path, "[config]\nversion = 1\n"), env={})


def test_unsupported_config_version_is_reported_before_unknown_keys(
    tmp_path: Path,
) -> None:
    """Unsupported versionはfuture key検証より先に報告される。"""
    config_path = _write(
        tmp_path,
        """
        [config]
        version = 1

        [future_section]
        enabled = true
        """,
    )

    with pytest.raises(ConfigError, match="Unsupported runtime config version: 1"):
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


def test_version_two_rejects_unknown_keys(tmp_path: Path) -> None:
    """Version 2ではstrict key検証を維持する。"""
    config_path = _write(
        tmp_path,
        """
        [config]
        version = 2

        [server]
        address = "localhost"
        """,
    )

    with pytest.raises(ConfigError, match=r"server\.address"):
        load_runtime_config(config_path, env={})


def test_v2_rejects_policy_detail_outside_advanced(tmp_path: Path) -> None:
    """詳細policyを通常namespaceへ置けない。"""
    path = _write(
        tmp_path,
        "[prompt_budget.local_low]\ntotal_max_chars = 1000\n",
    )
    with pytest.raises(ConfigError, match=r"prompt_budget\.local_low"):
        load_runtime_config(path, env={})


def test_v2_rejects_unknown_advanced_target(tmp_path: Path) -> None:
    """Advanced overrideは新しいprofileやsectionを作れない。"""
    path = _write(
        tmp_path,
        "[advanced.prompt_budget.custom.user_memory]\nmax_chars = 1000\n",
    )
    with pytest.raises(ConfigError, match=r"advanced\.prompt_budget\.custom"):
        load_runtime_config(path, env={})


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


def test_safety_env_is_applied(tmp_path: Path) -> None:
    """Safety env overrides are applied to the runtime config."""
    config = load_runtime_config(
        None,
        env={
            "IRIS_SAFETY_MODE": "basic",
            "IRIS_SAFETY_MAX_OUTPUT_CHARS": "1200",
        },
        cwd=tmp_path,
    )

    assert config.safety.mode == "basic"
    assert config.safety.max_output_chars == 1200


def test_invalid_safety_env_max_output_chars_is_rejected(tmp_path: Path) -> None:
    """Safety env max_output_chars must be an integer."""
    with pytest.raises(ConfigError, match="IRIS_SAFETY_MAX_OUTPUT_CHARS"):
        load_runtime_config(
            None,
            env={"IRIS_SAFETY_MAX_OUTPUT_CHARS": "invalid"},
            cwd=tmp_path,
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


def test_background_job_policy_is_config_gated_by_default(tmp_path: Path) -> None:
    """Background job pressure policy は明示設定まで permissive に保つ。"""
    config = load_runtime_config(None, env={}, cwd=tmp_path)

    assert config.learning.background_job_policy.enabled is False


def test_background_job_policy_can_be_enabled_explicitly(tmp_path: Path) -> None:
    """TOMLで明示した場合だけ pressure policy を有効化する。"""
    config = load_runtime_config(
        _write(
            tmp_path,
            """
            [learning.background_job_policy]
            enabled = true
            """,
        ),
        env={},
    )

    assert config.learning.background_job_policy.enabled is True
