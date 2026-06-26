"""Tests for runtime logging configuration."""

from __future__ import annotations

from typing import Any

import pytest

from iris.runtime.config.errors import ConfigError
from iris.runtime.config.logging import (
    LogFormat,
    LogLevel,
    RuntimeLoggingConfig,
    apply_logging_env,
    apply_logging_toml,
)


def test_logging_config_defaults() -> None:
    """Test default logging configuration."""
    config = RuntimeLoggingConfig()
    assert config.level == LogLevel.INFO
    assert config.format == LogFormat.TEXT
    assert config.file_path is None
    assert config.rotation == "10 MB"
    assert config.retention == "7 days"


def test_apply_logging_toml() -> None:
    """Test applying TOML to logging config."""
    base = RuntimeLoggingConfig()
    table: dict[str, Any] = {
        "level": "debug",
        "format": "json",
        "file_path": ".iris/test.log",
        "rotation": "5 MB",
        "retention": "3 days",
    }
    config = apply_logging_toml(base, table)

    assert config.level == LogLevel.DEBUG
    assert config.format == LogFormat.JSON
    assert config.file_path == ".iris/test.log"
    assert config.rotation == "5 MB"
    assert config.retention == "3 days"


def test_apply_logging_env() -> None:
    """Test applying env vars to logging config."""
    base = RuntimeLoggingConfig()
    env = {
        "IRIS_LOG_LEVEL": "trace",
        "IRIS_LOG_FORMAT": "json",
        "IRIS_LOG_FILE": ".iris/test_env.log",
    }
    config = apply_logging_env(base, env)

    assert config.level == LogLevel.TRACE
    assert config.format == LogFormat.JSON
    assert config.file_path == ".iris/test_env.log"


def test_apply_logging_invalid_level() -> None:
    """Test invalid log level."""
    base = RuntimeLoggingConfig()
    with pytest.raises(ConfigError, match="Invalid log level: INVALID"):
        apply_logging_toml(base, {"level": "INVALID"})
    with pytest.raises(ConfigError, match="Invalid log level: INVALID"):
        apply_logging_env(base, {"IRIS_LOG_LEVEL": "INVALID"})


def test_apply_logging_invalid_format() -> None:
    """Test invalid log format."""
    base = RuntimeLoggingConfig()
    with pytest.raises(ConfigError, match="Invalid log format: xml"):
        apply_logging_toml(base, {"format": "xml"})
    with pytest.raises(ConfigError, match="Invalid log format: xml"):
        apply_logging_env(base, {"IRIS_LOG_FORMAT": "xml"})
