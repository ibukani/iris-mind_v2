"""State / logging validation helpers."""

from __future__ import annotations

import pytest

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.logging import LogFormat, LogLevel, validate_format, validate_level
from iris.runtime.config.state import RuntimeStateBackend, validate_backend


def test_validate_backend_accepts_known_values() -> None:
    """Known backend values are normalized to the enum."""
    assert validate_backend("memory", "state.backend") is RuntimeStateBackend.MEMORY
    assert validate_backend("sqlite", "state.backend") is RuntimeStateBackend.SQLITE


def test_validate_backend_rejects_unknown_value() -> None:
    """Unknown backend values raise ConfigError."""
    with pytest.raises(ConfigError, match=r"Invalid state\.backend: postgres"):
        validate_backend("postgres", "state.backend")


def test_validate_level_accepts_case_insensitive_values() -> None:
    """Log levels normalize to the enum."""
    assert validate_level("trace") is LogLevel.TRACE
    assert validate_level("info") is LogLevel.INFO


def test_validate_level_rejects_unknown_value() -> None:
    """Unknown log levels raise ConfigError."""
    with pytest.raises(ConfigError, match="Invalid log level: verbose"):
        validate_level("verbose")


def test_validate_format_accepts_known_values() -> None:
    """Known log formats normalize to the enum."""
    assert validate_format("text") is LogFormat.TEXT
    assert validate_format("json") is LogFormat.JSON


def test_validate_format_rejects_unknown_value() -> None:
    """Unknown log formats raise ConfigError."""
    with pytest.raises(ConfigError, match="Invalid log format: xml"):
        validate_format("xml")
