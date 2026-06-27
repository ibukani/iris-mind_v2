"""Runtime auth config tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from iris.runtime.config import ConfigError, load_runtime_config


def test_default_local_only_auth_config_is_valid(tmp_path: Path) -> None:
    """Default remains local_dev + local_only=true."""
    config = load_runtime_config(_write(tmp_path, ""), env={})

    assert config.server.local_only
    assert config.auth.mode == "local_dev"


def test_remote_local_dev_auth_is_rejected(tmp_path: Path) -> None:
    """Remote bind cannot use local_dev auth mode."""
    with pytest.raises(ConfigError, match=r"auth\.mode='required'"):
        load_runtime_config(
            _write(
                tmp_path,
                """
                [server]
                local_only = false
                """,
            ),
            env={},
        )


def test_remote_required_auth_requires_tls_by_default(tmp_path: Path) -> None:
    """Remote auth-required bind requires TLS unless unsafe override is set."""
    with pytest.raises(ConfigError, match="requires TLS"):
        load_runtime_config(
            _write(
                tmp_path,
                """
                [server]
                local_only = false

                [auth]
                mode = "required"
                """,
            ),
            env={},
        )


def test_remote_required_auth_allows_explicit_insecure_override(tmp_path: Path) -> None:
    """Unsafe remote insecure mode is accepted only when explicit."""
    config = load_runtime_config(
        _write(
            tmp_path,
            """
            [server]
            local_only = false

            [auth]
            mode = "required"
            allow_insecure_remote = true
            """,
        ),
        env={},
    )

    assert not config.server.local_only
    assert config.auth.mode == "required"
    assert config.auth.allow_insecure_remote


def test_remote_required_auth_rejects_tls_disabled_even_if_require_tls_is_false(
    tmp_path: Path,
) -> None:
    """require_tls_for_remote=false does not bypass the remote TLS requirement."""
    with pytest.raises(ConfigError, match="requires TLS"):
        load_runtime_config(
            _write(
                tmp_path,
                """
                [server]
                local_only = false

                [auth]
                mode = "required"
                require_tls_for_remote = false
                allow_insecure_remote = false
                """,
            ),
            env={},
        )


def test_remote_required_auth_accepts_tls(tmp_path: Path) -> None:
    """Remote bind is accepted if TLS is enabled."""
    config = load_runtime_config(
        _write(
            tmp_path,
            """
            [server]
            local_only = false

            [server.tls]
            enabled = true
            cert_chain_path = "dummy.crt"
            private_key_path = "dummy.key"

            [auth]
            mode = "required"
            """,
        ),
        env={},
    )

    assert not config.server.local_only
    assert config.auth.mode == "required"
    assert config.server.tls.enabled


def _write(tmp_path: Path, content: str) -> str:
    path = tmp_path / "runtime.toml"
    path.write_text(content)
    return str(path)
